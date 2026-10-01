"""Downloads de voz gratuitos e diagnóstico da API local."""
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from ciencia_voz.local import available_models, download_kokoro

base = Path(__file__).resolve().parent
load_dotenv(base / ".env")
parser = argparse.ArgumentParser()
parser.add_argument("--baixar-voz", action="store_true")
parser.add_argument("--verificar-ollama", action="store_true")
args = parser.parse_args()
if args.baixar_voz:
    folder = Path(os.getenv("KOKORO_MODELS_DIR", "models"))
    if not folder.is_absolute():
        folder = base / folder
    download_kokoro(folder, lambda n, total: print(f"Kokoro: arquivo {n}/{total} pronto", flush=True))
    print(f"Voz local disponível em: {folder}")
if args.verificar_ollama:
    models = available_models(os.getenv("OLLAMA_URL", "http://localhost:11434"))
    print("Modelos locais:", ", ".join(models))
    configured = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    print(f"Modelo configurado: {configured}")
    if configured not in models:
        print(f"Ainda não instalado. Execute no container: ollama pull {configured}")
