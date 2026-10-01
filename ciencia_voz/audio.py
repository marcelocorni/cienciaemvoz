from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Callable
import unicodedata
import uuid
import zipfile

import imageio_ffmpeg
from openai import OpenAI

from .science import chunk_text


@dataclass
class Track:
    title: str
    text: str
    first_page: int
    last_page: int


def slug(title: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-")[:70] or "secao"


def join_mp3(parts: list[Path], destination: Path) -> None:
    """Decode/re-encode streams: never concatenate raw MP3 bytes."""
    if not parts:
        raise ValueError("Nenhum trecho de áudio foi produzido.")
    if len(parts) == 1:
        destination.write_bytes(parts[0].read_bytes())
        return
    # Generated numbered relative names, not user paths; safe concat list.
    listing = parts[0].parent / "concat.txt"
    listing.write_text("\n".join(f"file '{part.name}'" for part in parts), encoding="utf-8")
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "1", "-i", str(listing.resolve()),
         "-vn", "-codec:a", "libmp3lame", "-b:a", "128k", str(destination.resolve())],
        capture_output=True, timeout=600,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode or not destination.exists():
        raise RuntimeError("Não foi possível juntar os trechos de áudio com FFmpeg.")


def export_tracks(client: OpenAI, tracks: list[Track], output_root: Path, *,
                  voice: str = "coral", speed: float = 1.0,
                  model: str = "gpt-4o-mini-tts", language: str = "Português brasileiro",
                  source_hash: str = "", progress: Callable[[int, int], None] = lambda *_: None,
                  synthesizer=None, metadata: dict | None = None) -> Path:
    if not tracks or any(not track.text.strip() for track in tracks):
        raise ValueError("Todas as seleções devem ter texto de narração.")
    if any("[" in t.text and re.search(r"\[(?:CONFERIR|ileg[ií]vel|P[aá]gina sem|s[ií]mbolo ileg)", t.text, re.I)
           for t in tracks):
        raise ValueError("Corrija os marcadores de conteúdo ilegível ou a conferir antes de gerar áudio.")
    root = output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    # Generate outside the watched Streamlit project. Windows watchers can hold
    # directory handles and deny renaming an otherwise complete output folder.
    staging = tempfile.TemporaryDirectory(prefix="ciencia-voz-export-")
    folder = Path(staging.name)
    completed = None
    created_output = False
    jobs = [(track, chunk_text(track.text, limit=700 if synthesizer else 2800)) for track in tracks]
    total = sum(len(chunks) for _, chunks in jobs)
    done, entries = 0, []
    try:
        for index, (track, chunks) in enumerate(jobs, 1):
            basename = f"{index:03d}-{slug(track.title)}"
            with tempfile.TemporaryDirectory(prefix="ciencia-voz-") as temp:
                parts = []
                for part_number, chunk in enumerate(chunks):
                    part = Path(temp) / f"part-{part_number:05d}.mp3"
                    if synthesizer:
                        synthesizer(chunk, part)
                    else:
                        args = dict(model=model, voice=voice, input=chunk, response_format="mp3", speed=speed)
                        if model.startswith("gpt-4o-mini-tts"):
                            args["instructions"] = (
                                f"Narre com clareza acadêmica. Idioma/convenção de fala: {language}. "
                                "Preserve o texto e o idioma original. Articule termos científicos, "
                                "números e siglas. Faça pausas naturais entre fórmulas e parágrafos. "
                                "Não resuma nem acrescente palavras."
                            )
                        with client.audio.speech.with_streaming_response.create(**args) as response:
                            response.stream_to_file(part)
                    if not part.exists() or part.stat().st_size < 100:
                        raise RuntimeError("O serviço de voz retornou um arquivo vazio ou inválido.")
                    parts.append(part)
                    done += 1
                    progress(done, total)
                mp3 = folder / f"{basename}.mp3"
                join_mp3(parts, mp3)
            (folder / f"{basename}.txt").write_text(track.text, encoding="utf-8")
            entries.append({**asdict(track), "text": None, "mp3": mp3.name,
                            "transcript": f"{basename}.txt",
                            "text_sha256": hashlib.sha256(track.text.encode()).hexdigest(),
                            "chunks": len(chunks)})
        manifest = {"created_utc": datetime.now(timezone.utc).isoformat(),
                    "source_sha256": source_hash, "voice": voice, "speed": speed,
                    "tts_model": model, "language": language,
                    "ai_generated_voice": True, "tracks": entries,
                    "backend": "local" if synthesizer else "openai", "preparation": metadata or {}}
        (folder / "manifesto.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "LEIA-ME.txt").write_text(
            "Voz gerada por inteligência artificial.\nConfira as transcrições, especialmente fórmulas.\n"
            "As páginas indicadas são as páginas físicas do PDF.\n", encoding="utf-8")
        # Publish only after every track is ready. Copying closed files avoids
        # renaming a directory watched by Streamlit; manifest is the commit marker.
        completed = root / run_id
        completed.mkdir()
        created_output = True
        for file in folder.iterdir():
            if file.name != "manifesto.json":
                shutil.copy2(file, completed / file.name)
        shutil.copy2(folder / "manifesto.json", completed / "manifesto.json")
        return completed
    except Exception:
        # Only this function's UUID-scoped job is removed, never the output root.
        if created_output:
            if completed.resolve().parent != root or completed.name != run_id:
                raise RuntimeError("Caminho de limpeza fora da pasta desta geração.")
            shutil.rmtree(completed)
        raise
    finally:
        staging.cleanup()


def zip_package(folder: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(folder.iterdir()):
            if file.is_file() and file.suffix in {".mp3", ".txt", ".json"}:
                archive.write(file, file.name)
    return buffer.getvalue()
