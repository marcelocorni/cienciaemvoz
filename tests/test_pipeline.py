import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import zipfile

import imageio_ffmpeg
import pymupdf
import pytest

from ciencia_voz.audio import Track, export_tracks, slug, zip_package
from ciencia_voz.demo import demo_pdf
from ciencia_voz.pdf import (analyze, custom_section, deduplicate, from_markdown,
                             make_sections, render_page)
from ciencia_voz.science import (apply_glossary, chunk_text, local_narration,
                                parse_glossary, scientific_narration, _vision)


def test_bookmark_hierarchy_and_same_page_boundaries():
    doc = analyze(demo_pdf())
    assert len(doc.sections) == 4
    chapter, subsection, methods, procedure = doc.sections
    assert chapter.level == 1 and subsection.level == 2
    assert subsection.start > chapter.start
    assert chapter.end == subsection.end == methods.start
    assert "E = m c^2" in doc.text(chapter)
    assert "1 Introducao" not in doc.text(subsection)
    assert "2 Metodos" not in doc.text(subsection)
    assert doc.page_range(subsection) == (1, 1)
    assert render_page(demo_pdf(), 0).startswith(b"\x89PNG")


def test_deduplicate_parent_children_and_partial_overlap():
    doc = analyze(demo_pdf())
    selected, skipped = deduplicate(doc.sections[:2])
    assert len(selected) == 1 and len(skipped) == 1
    a = custom_section(doc, "Tudo", 1, 2)
    b = custom_section(doc, "Página um", 1, 1)
    assert deduplicate([a, b])[0] == [a]
    sections = make_sections([(0, "A", 1, "test"), (5, "B", 1, "test")], 10)
    sections[0].end = 7
    with pytest.raises(ValueError, match="sobrepostos"):
        deduplicate(sections)


def test_heuristics_without_bookmarks():
    doc = analyze(demo_pdf(), mode="headings")
    assert [s.level for s in doc.sections] == [1, 2, 1, 2]
    assert all(s.source == "títulos detectados" for s in doc.sections)


def test_scanned_fallback_and_ocr_structure():
    pdf = pymupdf.open()
    pdf.new_page()
    raw = pdf.tobytes()
    pdf.close()
    doc = analyze(raw)
    assert doc.scanned_pages == [1]
    assert doc.sections[0].title == "Página 1"
    recovered = from_markdown(["# Introdução\nTexto\n## Fórmula\n$E=mc^2$"], doc)
    assert [s.level for s in recovered.sections] == [1, 2]
    assert "$E=mc^2$" in recovered.text(recovered.sections[1])


def test_password_invalid_pdf_and_ranges():
    with pytest.raises(ValueError, match="válido"):
        analyze(b"not a pdf")
    pdf = pymupdf.open(stream=demo_pdf(), filetype="pdf")
    locked = pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="science")
    pdf.close()
    with pytest.raises(ValueError, match="protegido"):
        analyze(locked)
    assert analyze(locked, "science").pages == 2
    doc = analyze(demo_pdf(), mode="pages")
    assert len(doc.sections) == 2
    with pytest.raises(ValueError):
        custom_section(doc, "Bad", 2, 1)
    assert doc.page_range(custom_section(doc, "Tudo", 1, 2)) == (1, 2)


def test_glossary_boundaries_and_non_cascading_replacement():
    glossary = parse_glossary("ATP = a tê pê\nm = metro\na tê pê = errado")
    assert apply_glossary("ATP, atp; campo m", glossary) == "a tê pê, a tê pê; campo metro"
    assert local_narration("experi-\nmental\nTexto", {}) == "experimental Texto"
    with pytest.raises(ValueError):
        parse_glossary("entrada inválida")


@pytest.mark.parametrize("text", ["word " * 5000, "x" * 10000, "α. β? γ;\n\n" * 1000, "a" * 2800, ""])
def test_chunk_limits_and_content(text):
    chunks = chunk_text(text)
    assert all(0 < len(x) <= 2800 for x in chunks)
    assert "".join("".join(chunks).split()) == "".join(text.split())


def test_vision_rejects_truncated_output():
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: SimpleNamespace(
        status="incomplete", output_text="texto parcial")))
    with pytest.raises(ValueError, match="interrompida"):
        _vision(fake, "model", "instruction", "prompt", b"png")


def test_scientific_selection_request_and_no_server_storage():
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status="completed", output_text="E é igual a m vezes c ao quadrado.")
    fake = SimpleNamespace(responses=SimpleNamespace(create=create))
    data = demo_pdf()
    doc = analyze(data)
    text = scientific_narration(fake, "gpt-4.1-mini", data, doc, doc.sections[1], "", "Português", lambda *_: None)
    assert "quadrado" in text
    assert calls[0]["store"] is False
    selected_input = calls[0]["input"][0]["content"][0]["text"]
    assert "1 Introducao" not in selected_input
    assert "2 Metodos" not in selected_input
    assert "E = m c^2" in selected_input


@pytest.fixture
def mp3_sample(tmp_path):
    target = tmp_path / "sample.mp3"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=0.3",
                    "-codec:a", "libmp3lame", str(target)], check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return target.read_bytes()


class FakeSpeech:
    def __init__(self, data, fail_at=None):
        self.data, self.calls, self.fail_at = data, [], fail_at

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_at == len(self.calls):
            raise RuntimeError("Simulated failure")
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def stream_to_file(self, path):
        path.write_bytes(self.data)


def fake_client(speech):
    return SimpleNamespace(audio=SimpleNamespace(speech=SimpleNamespace(with_streaming_response=speech)))


def test_mp3_join_and_zip_manifest(tmp_path, mp3_sample):
    speech = FakeSpeech(mp3_sample)
    folder = export_tracks(fake_client(speech), [Track("../Método: energia", "Texto. " * 600, 1, 2)],
                           tmp_path / "audio", source_hash="pdfhash")
    assert len(speech.calls) > 1
    manifest = json.loads((folder / "manifesto.json").read_text(encoding="utf-8"))
    assert manifest["source_sha256"] == "pdfhash"
    track = manifest["tracks"][0]
    assert track["first_page"] == 1 and track["last_page"] == 2
    assert "/" not in track["mp3"] and ".." not in track["mp3"]
    # Decode the completed file: invalid byte concatenation would not be sufficient.
    result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                             "-i", str(folder / track["mp3"]), "-f", "null", "-"], capture_output=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0
    with zipfile.ZipFile(io.BytesIO(zip_package(folder))) as archive:
        assert track["mp3"] in archive.namelist()
        assert track["transcript"] in archive.namelist()
        assert "manifesto.json" in archive.namelist()


def test_failure_cleans_only_current_job(tmp_path, mp3_sample):
    old = tmp_path / "old-job"
    old.mkdir()
    (old / "keep.txt").write_text("Keep")
    speech = FakeSpeech(mp3_sample, fail_at=2)
    with pytest.raises(RuntimeError, match="Simulated"):
        export_tracks(fake_client(speech), [Track("A", "Word. " * 900, 1, 1)], tmp_path)
    assert old.exists() and (old / "keep.txt").read_text() == "Keep"
    assert not any(x.name.startswith(".pending-") for x in tmp_path.iterdir())
    assert not any(x.is_dir() and x != old for x in tmp_path.iterdir())


def test_unresolved_and_empty_text_never_call_api(tmp_path):
    speech = FakeSpeech(b"unused")
    for text in ["", "[CONFERIR: equação]", "[ilegível]", "[Página sem texto extraível.]"]:
        with pytest.raises(ValueError):
            export_tracks(fake_client(speech), [Track("A", text, 1, 1)], tmp_path)
    assert not speech.calls
    assert slug("CON / ../../") == "CON"


def test_publish_without_directory_rename_on_windows(tmp_path, mp3_sample, monkeypatch):
    def blocked_rename(*args, **kwargs):
        raise PermissionError("Windows watcher prevents directory rename")
    monkeypatch.setattr(Path, "rename", blocked_rename)
    speech = FakeSpeech(mp3_sample)
    folder = export_tracks(fake_client(speech), [Track("Resumo", "Texto científico.", 1, 1)], tmp_path)
    assert folder.parent == tmp_path
    assert (folder / "manifesto.json").exists()
    assert len(list(folder.glob("*.mp3"))) == 1


def test_publication_failure_cleans_output_and_commits_manifest_last(tmp_path, mp3_sample, monkeypatch):
    import shutil
    copied = []
    original = shutil.copy2
    def copy(source, target):
        copied.append(Path(source).name)
        if Path(source).name == "manifesto.json":
            raise PermissionError("Simulated copy failure")
        return original(source, target)
    monkeypatch.setattr(shutil, "copy2", copy)
    speech = FakeSpeech(mp3_sample)
    output = tmp_path / "audio"
    with pytest.raises(PermissionError, match="copy failure"):
        export_tracks(fake_client(speech), [Track("Resumo", "Texto científico.", 1, 1)], output)
    assert copied[-1] == "manifesto.json"
    assert not list(output.iterdir())
