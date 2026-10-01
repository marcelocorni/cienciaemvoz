from __future__ import annotations

import hashlib
import json
import os
import logging
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from ciencia_voz.audio import Track, export_tracks, zip_package
from ciencia_voz.demo import demo_pdf
from ciencia_voz.pdf import analyze, custom_section, deduplicate, render_page
from ciencia_voz.science import apply_glossary, chunk_text, local_narration, parse_glossary
from ciencia_voz.local import (available_models, docling_document, download_kokoro, kokoro_engine,
                               narrate_ollama, synthesize_kokoro)

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")
st.set_page_config(page_title="Ciência em Voz", page_icon="🎧", layout="wide")
models_dir = Path(os.getenv("KOKORO_MODELS_DIR", "models"))
if not models_dir.is_absolute():
    models_dir = BASE / models_dir


def signature(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def friendly_error(exc: Exception) -> str:
    # Avoid leaking service response bodies, uploaded content or credentials.
    from openai import AuthenticationError, RateLimitError, APIConnectionError, APIStatusError
    if isinstance(exc, AuthenticationError):
        return "A chave da API foi recusada. Confira a chave e as permissões da conta."
    if isinstance(exc, RateLimitError):
        return "A API atingiu um limite de uso ou saldo. Confira a conta e tente novamente."
    if isinstance(exc, APIConnectionError):
        return "Não foi possível conectar ao serviço. Confira a internet e tente novamente."
    if isinstance(exc, APIStatusError):
        return "O serviço recusou a solicitação. Confira o modelo e tente novamente."
    if isinstance(exc, (ValueError, RuntimeError)):
        return str(exc)
    if isinstance(exc, PermissionError):
        return "Não foi possível gravar o áudio. Confira as permissões da pasta de saída e feche arquivos abertos em outro programa."
    if isinstance(exc, OSError):
        return f"Falha ao acessar arquivos ou executar o conversor de áudio ({type(exc).__name__}). Confira a pasta de saída e o FFmpeg."
    if isinstance(exc, TypeError):
        return "Há uma incompatibilidade entre os componentes de áudio carregados. Reinicie a aplicação para carregar a versão atualizada."
    return "Não foi possível concluir a operação. Verifique o arquivo, a conexão e o espaço disponível."


with st.sidebar:
    st.markdown("### Sua biblioteca, em voz")
    st.caption("Do PDF à escuta, com revisão científica.")
    st.success("Processamento local · sem API paga")
    ollama_url = st.text_input("Endereço do Ollama", os.getenv("OLLAMA_URL", "http://localhost:11434"))
    ollama_model = st.text_input("Modelo do Ollama", os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    if st.button("Verificar conexão e modelos"):
        try:
            installed = available_models(ollama_url)
            st.success("Ollama conectado. Modelos de texto: " + ", ".join(installed))
            if ollama_model not in installed:
                st.warning(f"Baixe {ollama_model} ou informe um dos modelos instalados acima.")
        except Exception as exc:
            st.error(friendly_error(exc))
    voice_language = st.selectbox("Idioma da voz", ["Português brasileiro", "English", "Español"])
    voice_options = {"Português brasileiro": ["pf_dora", "pm_alex", "pm_santa"],
                     "English": ["af_heart", "am_michael"], "Español": ["ef_dora", "em_alex"]}
    voice = st.selectbox("Voz Kokoro", voice_options[voice_language])
    voice_lang = {"Português brasileiro": "pt-br", "English": "en-us", "Español": "es"}[voice_language]
    speed = st.slider("Velocidade", .5, 1.5, 1.0, .05)
    language = st.selectbox("Idioma para a leitura de fórmulas", ["Português brasileiro", "English", "Español"])
    st.caption("O idioma dos parágrafos é preservado.")
    glossary_raw = st.text_area("Pronúncias científicas", placeholder="ATP = a tê pê\nNaCl = cloreto de sódio",
                               help="Uma entrada por linha: termo = pronúncia. Aplicado ao texto antes da revisão.")
    st.caption("Docling extrai o PDF; Ollama prepara as fórmulas; Kokoro gera a voz localmente.")
    st.caption("A voz não traduz o conteúdo: escolha o idioma correspondente ao texto.")
    ready_voice = all((models_dir / name).exists() for name in ["kokoro-v1.0.onnx", "voices-v1.0.bin"])
    if ready_voice:
        st.caption("Arquivos de voz instalados.")
    elif st.button("Baixar arquivos de voz Kokoro"):
        bar = st.progress(0, text="Baixando modelo e vozes…")
        try:
            download_kokoro(models_dir, lambda n, total: bar.progress(n / total))
            st.rerun()
        except Exception as exc:
            st.error(friendly_error(exc))
        finally:
            bar.empty()
    with st.expander("Configurações avançadas"):
        docling_container = st.text_input("Container Docling", os.getenv("DOCLING_CONTAINER", "dissertacao-rag-docling-1"),
                                          help="Vazio: usa Docling instalado no Python local.")
        formula_enrichment = st.checkbox("Reconhecer fórmulas no Docling", value=True)
        st.caption("O primeiro uso pode baixar os modelos gratuitos do Docling. Depois, a extração roda localmente.")

st.title("Ciência em Voz")
st.markdown("Transforme os capítulos que importam em uma biblioteca de áudio.")
st.caption("1. Envie o PDF  ·  2. Escolha o conteúdo  ·  3. Revise a narração  ·  4. Baixe os MP3")

st.subheader("1 · Seu documento")
upload = st.file_uploader("Envie um artigo, livro ou tese", type=["pdf"],
                          help="Até 50 MB e 500 páginas. Os números de página correspondem às páginas físicas do PDF.")
if st.button("Experimentar com um PDF de exemplo"):
    st.session_state["demo_data"] = demo_pdf()
data = upload.getvalue() if upload else st.session_state.get("demo_data")
name = upload.name if upload else "exemplo-cientifico.pdf"
if not data:
    st.info("Envie um PDF para identificar capítulos, seções e subseções, ou abra o exemplo.")
    st.stop()

password = st.text_input("Senha do PDF, se necessário", type="password")
mode_label = st.radio("Como identificar a estrutura", ["Automático (sumário e títulos)", "Apenas títulos", "Por páginas"], horizontal=True)
mode = {"Automático (sumário e títulos)": "auto", "Apenas títulos": "headings", "Por páginas": "pages"}[mode_label]
document_key = signature([hashlib.sha256(data).hexdigest(), password, mode])
if st.session_state.get("document_key") != document_key:
    for field in ["doc", "prepared", "prepared_key", "package", "manual"]:
        st.session_state.pop(field, None)
    st.session_state["document_key"] = document_key

if st.button("Identificar estrutura", type="primary"):
    try:
        with st.spinner("Lendo o PDF e procurando títulos…"):
            st.session_state["doc"] = analyze(data, password, mode)
            st.session_state["manual"] = []
            st.session_state.pop("prepared", None)
            st.session_state.pop("package", None)
    except Exception as exc:
        st.error(friendly_error(exc))
doc = st.session_state.get("doc")
if doc is None:
    st.stop()

a, b, c = st.columns(3)
a.metric("Páginas", doc.pages)
b.metric("Capítulos e seções", len(doc.sections))
c.metric("Páginas com pouco texto", len(doc.scanned_pages))
with st.expander("Qualidade da extração e leitura visual"):
    for warning in doc.warnings:
        st.warning(warning)
    st.write(f"Docling reconstrói as {doc.pages} páginas localmente, com OCR, ordem de leitura e reconhecimento de fórmulas. "
             "Use esta opção para documentos digitalizados, fórmulas ou várias colunas. Pode levar alguns minutos.")
    if st.button("Reconstruir texto e fórmulas com Docling"):
        try:
            with st.spinner("Processando com Docling local; aguarde a conversão completa…"):
                st.session_state["doc"] = docling_document(data, password, docling_container, formula_enrichment)
            st.session_state["manual"] = []
            st.session_state.pop("prepared", None)
            st.session_state.pop("package", None)
            st.rerun()
        except Exception as exc:
            st.error(friendly_error(exc))

st.subheader("2 · Escolha o que deseja ouvir")
st.caption("Um capítulo inclui suas subseções. Seleções contidas em outra seleção são agrupadas em um único MP3.")
with st.expander("Adicionar uma seleção manual por páginas"):
    with st.form("manual-range-" + document_key):
        title = st.text_input("Título da seleção")
        left, right = st.columns(2)
        first = left.number_input("Primeira página", min_value=1, max_value=doc.pages, value=1)
        last = right.number_input("Última página", min_value=1, max_value=doc.pages, value=doc.pages)
        if st.form_submit_button("Adicionar seleção"):
            try:
                section = custom_section(doc, title, int(first), int(last))
                if not any(s.id == section.id for s in st.session_state.get("manual", [])):
                    st.session_state.setdefault("manual", []).append(section)
            except ValueError as exc:
                st.error(str(exc))

sections = doc.sections + st.session_state.get("manual", [])
tree_key = signature([document_key, [(s.id, s.title, s.start, s.end) for s in sections]])
rows = []
for section in sections:
    first, last = doc.page_range(section)
    rows.append({"Ouvir": False, "Conteúdo": "　" * (section.level - 1) + section.title,
                 "Nível": section.level, "Páginas": f"{first}–{last}", "Origem": section.source})
edited = st.data_editor(rows, key="tree-" + tree_key, hide_index=True, width="stretch",
                        disabled=["Conteúdo", "Nível", "Páginas", "Origem"],
                        column_config={"Ouvir": st.column_config.CheckboxColumn("Ouvir", width="small")})
try:
    selected, skipped = deduplicate([s for s, row in zip(sections, edited) if row["Ouvir"]])
except ValueError as exc:
    st.error(str(exc))
    selected, skipped = [], []
if skipped:
    st.info("Incluídas na seleção maior: " + ", ".join(skipped))

with st.expander("Conferir o PDF original e o texto extraído"):
    page_number = st.number_input("Página para visualizar", 1, doc.pages, 1)
    left, right = st.columns(2)
    left.image(render_page(data, int(page_number) - 1, password), width="stretch")
    right.text_area("Texto dessa página", "\n".join(x.text for x in doc.lines if x.page == page_number - 1),
                    height=480, disabled=True)

if not selected:
    st.info("Marque os capítulos, seções ou páginas que deseja ouvir.")
    st.stop()

st.subheader("3 · Prepare e revise a narração")
prep_mode = st.radio("Preparação", ["Leitura científica com Ollama", "Texto local, com revisão manual"], horizontal=True)
use_ai = prep_mode.startswith("Leitura")
try:
    glossary = parse_glossary(glossary_raw)
except ValueError as exc:
    st.error(str(exc))
    st.stop()
prep_key = signature([tree_key, [(s.id, s.start, s.end) for s in selected], prep_mode,
                      glossary, language, ollama_url, ollama_model])
st.write(f"{len(selected)} arquivo(s) de áudio serão gerados, um por seleção.")
if use_ai:
    st.caption("O texto selecionado será enviado ao seu Ollama. Fórmulas serão escritas por extenso; "
               "trechos ambíguos serão marcados para conferência.")
    if not all(s.source == "Docling local" for s in selected):
        st.info("Se houver fórmulas ou várias colunas, reconstrua primeiro com Docling no painel de qualidade da extração.")
else:
    st.warning("A preparação local não interpreta fórmulas complexas. Escreva fórmulas, unidades e símbolos por extenso na revisão.")
if st.button("Preparar textos da seleção", type="primary"):
    bar = st.progress(0, text="Preparando narração…")
    prepared = []
    try:
        for index, section in enumerate(selected):
            if use_ai:
                text = narrate_ollama(
                    ollama_url, ollama_model, doc.text(section), language,
                    lambda n, total: bar.progress((index + n / total) / len(selected),
                                                 text=f"Preparando seleção {index + 1} de {len(selected)}"))
                text = apply_glossary(text, glossary)
            else:
                text = local_narration(doc.text(section), glossary)
                bar.progress((index + 1) / len(selected))
            first, last = doc.page_range(section)
            prepared.append({"title": section.title, "text": text, "first_page": first, "last_page": last})
        st.session_state["prepared"] = prepared
        st.session_state["prepared_key"] = prep_key
        st.session_state["edit_revision"] = st.session_state.get("edit_revision", 0) + 1
        st.session_state.pop("package", None)
    except Exception as exc:
        logging.getLogger("ciencia_voz").exception("Falha na preparação da narração")
        st.error(friendly_error(exc))
        with st.expander("Detalhes do erro de preparação"):
            st.code(f"{type(exc).__name__}: {exc}", language="text")
    finally:
        bar.empty()

if st.session_state.get("prepared_key") != prep_key or not st.session_state.get("prepared"):
    st.info("Prepare os textos para revisar a pronúncia e as fórmulas antes de gerar áudio.")
    st.stop()

tracks = []
revision = st.session_state.get("edit_revision", 0)
for i, prepared in enumerate(st.session_state["prepared"]):
    with st.expander(f'{i + 1:02d} · {prepared["title"]}', expanded=True):
        st.caption(f'Páginas {prepared["first_page"]}–{prepared["last_page"]}')
        text = st.text_area("Texto que será narrado", prepared["text"], height=230,
                            key=f"narration-{prep_key}-{revision}-{i}")
        tracks.append(Track(prepared["title"], text, prepared["first_page"], prepared["last_page"]))
        st.download_button("Baixar transcrição", text.encode("utf-8"), f"transcricao-{i + 1:03d}.txt",
                           mime="text/plain", key=f"txt-{i}")

chars = sum(len(t.text) for t in tracks)
minutes = round(sum(len(t.text.split()) for t in tracks) / (140 * speed))
requests = sum(len(chunk_text(t.text, limit=700)) for t in tracks)
st.caption(f"{chars:,} caracteres · {requests} trecho(s) de voz local · duração aproximada: {max(1, minutes)} min.")
review_key = signature([prep_key, [t.text for t in tracks]])
reviewed = st.checkbox("Revisei o texto, as fórmulas e as pronúncias", key="review-" + review_key)

st.subheader("4 · Gere e baixe seus áudios")
st.caption("Voz gerada por inteligência artificial. Os MP3 e as transcrições serão salvos em uma pasta própria para esta geração.")
if not ready_voice:
    st.info("Baixe os arquivos de voz Kokoro na barra lateral para gerar MP3 sem serviços pagos.")
if st.button("Gerar arquivos MP3", type="primary", disabled=not (reviewed and ready_voice)):
    bar = st.progress(0, text="Gerando áudio…")
    try:
        root = Path(os.getenv("AUDIO_OUTPUT_DIR", "audios"))
        if not root.is_absolute():
            root = BASE / root
        engine = kokoro_engine(str(models_dir.resolve()))
        folder = export_tracks(None, tracks, root, voice=voice, speed=speed,
                               model="kokoro-82m-onnx-v1.0", language=voice_language,
                               synthesizer=lambda text, path: synthesize_kokoro(engine, text, path, voice, speed, voice_lang),
                               metadata={"engine": "ollama" if use_ai else "manual", "model": ollama_model if use_ai else None},
                               source_hash=hashlib.sha256(data).hexdigest(),
                               progress=lambda n, total: bar.progress(n / total, text=f"Áudio: trecho {n} de {total}"))
        st.session_state["package"] = str(folder)
        st.session_state["package_settings"] = signature([review_key, voice, speed, voice_language])
    except Exception as exc:
        logging.getLogger("ciencia_voz").exception("Falha na geração de arquivos MP3")
        st.error(friendly_error(exc))
        with st.expander("Detalhes do erro de geração"):
            st.code(f"{type(exc).__name__}: {exc}", language="text")
    finally:
        bar.empty()

package = st.session_state.get("package")
if package:
    folder = Path(package)
    if st.session_state.get("package_settings") != signature([review_key, voice, speed, voice_language]):
        st.warning("Os arquivos abaixo pertencem à geração anterior. Gere novamente para incorporar as alterações.")
    st.success("Arquivos prontos para ouvir e baixar.")
    st.caption(f"Pasta no computador que executa o aplicativo: {folder}")
    st.download_button("Baixar pacote completo (.zip)", zip_package(folder),
                       "ciencia-em-voz.zip", mime="application/zip", type="primary")
    manifest = json.loads((folder / "manifesto.json").read_text(encoding="utf-8"))
    for entry in manifest["tracks"]:
        st.markdown(f'**{entry["title"]}**')
        audio = (folder / entry["mp3"]).read_bytes()
        st.audio(audio, format="audio/mpeg")
        st.download_button("Baixar MP3", audio, entry["mp3"], mime="audio/mpeg", key=entry["mp3"])
