import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import requests

from ciencia_voz.audio import Track, export_tracks
from ciencia_voz.demo import demo_pdf
from ciencia_voz.local import (available_models, docling_document, document_from_items,
                               narrate_ollama, narration_chunks, synthesize_kokoro)


def response(data, status=200):
    return SimpleNamespace(status_code=status, json=lambda: data, raise_for_status=lambda: None)


def test_ollama_models_filters_embedding(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: response({"models": [
        {"name": "gpt-oss:20b", "capabilities": ["completion"]},
        {"name": "bge-m3", "capabilities": ["embedding"]}]}))
    assert available_models("http://localhost:11434/") == ["gpt-oss:20b"]


def test_ollama_requests_chunks_and_thinking(monkeypatch):
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return response({"done": True, "done_reason": "stop", "message": {"content": "E é igual a m vezes c ao quadrado."}})
    monkeypatch.setattr(requests, "post", post)
    result = narrate_ollama("http://localhost:11434/", "qwen3:8b", "$E=mc^2$. " * 250, "Português")
    assert "ao quadrado" in result and len(calls) > 1
    assert calls[0][0] == "http://localhost:11434/api/chat"
    assert calls[0][1]["think"] is False
    assert calls[0][1]["stream"] is False
    assert all(len(c[1]["messages"][1]["content"]) < 2000 for c in calls)
    narrate_ollama("http://localhost:11434", "gpt-oss:20b", "E=mc^2", "Português")
    assert calls[-1][1]["think"] == "low"


@pytest.mark.parametrize("data", [{"done": False}, {"done": True, "done_reason": "length"},
                                   {"done": True, "message": {"content": ""}}])
def test_ollama_rejects_incomplete(monkeypatch, data):
    monkeypatch.setattr(requests, "post", lambda *a, **k: response(data))
    with pytest.raises(ValueError):
        narrate_ollama("http://localhost:11434", "qwen3:8b", "Formula", "Português")


def test_ollama_missing_model_and_scan(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: response({}, status=404))
    with pytest.raises(ValueError, match="ollama pull qwen3:8b"):
        narrate_ollama("http://localhost:11434", "qwen3:8b", "Formula", "Português")
    with pytest.raises(ValueError, match="Docling"):
        narrate_ollama("http://localhost:11434", "qwen3:8b", "[Página sem texto extraível]", "Português")


def test_equation_is_never_split_between_requests():
    formula = "$f(x) = \\frac{" + "a + " * 100 + "b}{c}$"
    source = "texto " * 270 + formula + " fim " * 200
    chunks = narration_chunks(source)
    assert all(len(chunk) <= 1800 for chunk in chunks)
    assert any(formula in chunk for chunk in chunks)
    assert all(chunk.count("$") % 2 == 0 for chunk in chunks)
    assert "".join("".join(chunks).split()) == "".join(source.split())


def test_oversize_formula_requires_manual_review():
    with pytest.raises(ValueError, match="fórmula muito longa"):
        narration_chunks("$" + "x+" * 1000 + "y$")


def test_docling_mapping_preserves_hierarchy_and_formula():
    doc = document_from_items({"pages": 2, "entries": [
        {"page": 1, "text": "1 Modelo", "level": 1},
        {"page": 1, "text": "1.1 Formula", "level": 2},
        {"page": 1, "text": "$E=mc^2$", "level": 0},
        {"page": 2, "text": "2 Resultados", "level": 1},
    ]}, 2)
    assert doc.sections[0].end == doc.sections[1].end == doc.sections[2].start
    assert "$E=mc^2$" in doc.text(doc.sections[1])
    assert "2 Resultados" not in doc.text(doc.sections[1])
    assert doc.page_range(doc.sections[1]) == (1, 1)
    with pytest.raises(ValueError):
        document_from_items({"pages": 1, "entries": []}, 2)


def test_docling_worker_protocol(monkeypatch):
    captured = []
    def run(cmd, **kwargs):
        captured.append((cmd, json.loads(kwargs["input"])))
        data = {"pages": 2, "entries": [{"page": 1, "text": "1 Modelo", "level": 1},
                                         {"page": 2, "text": "2 Teste", "level": 1}]}
        return SimpleNamespace(returncode=0, stdout=("Log inicial\nCIENCIA_VOZ_RESULT=" + json.dumps(data)).encode())
    monkeypatch.setattr("ciencia_voz.local.subprocess.run", run)
    doc = docling_document(demo_pdf(), container="docling-existing")
    assert doc.pages == 2
    assert captured[0][0][:6] == ["docker", "exec", "-i", "docling-existing", "python", "-c"]
    assert captured[0][1]["formulas"] is True and "password" not in captured[0][1]


def test_kokoro_invalid_audio_blocks_export(tmp_path):
    engine = SimpleNamespace(create=lambda *a, **k: (np.array([np.nan]), 24000))
    with pytest.raises(ValueError, match="inválido"):
        synthesize_kokoro(engine, "Texto", tmp_path / "audio.mp3", "pf_dora", 1, "pt-br")
    assert not list(tmp_path.iterdir())


def test_export_local_never_calls_paid_client(tmp_path):
    calls = []
    def synth(text, path):
        calls.append(text)
        path.write_bytes(b"fake-mp3" * 100)
    folder = export_tracks(None, [Track("Local", "Energia em joules.", 1, 1)], tmp_path,
                           model="kokoro", voice="pf_dora", synthesizer=synth,
                           metadata={"engine": "ollama", "model": "qwen3:8b"})
    assert calls == ["Energia em joules."]
    manifest = json.loads((folder / "manifesto.json").read_text(encoding="utf-8"))
    assert manifest["backend"] == "local"
    assert manifest["preparation"]["model"] == "qwen3:8b"
