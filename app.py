from __future__ import annotations

import hashlib
import json
import os
import logging
import tempfile
import uuid
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from ciencia_voz.audio import Track, export_tracks, zip_package
from ciencia_voz.text_input import decode_txt, import_pronunciations
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

VOICE_OPTIONS = {"Português brasileiro": ["pf_dora", "pm_alex", "pm_santa"],
                 "English": ["af_heart", "am_michael"], "Español": ["ef_dora", "em_alex"]}
VOICE_LANGUAGES = {"Português brasileiro": "pt-br", "English": "en-us", "Español": "es"}


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
    voice_options = VOICE_OPTIONS
    voice = st.selectbox("Voz Kokoro", voice_options[voice_language])
    voice_lang = VOICE_LANGUAGES[voice_language]
    speed = st.slider("Velocidade", .5, 2.0, 1.0, .05)
    with st.expander("Ajustes da voz"):
        pitch = st.slider("Altura da voz (semitons)", -6.0, 6.0, 0.0, 0.5,
                          help="Negativo: mais grave. Positivo: mais aguda. A duração é preservada; ajustes grandes podem soar artificiais.")
        volume_db = st.slider("Volume (dB)", -12.0, 6.0, 0.0, 1.0)
        sentence_pause = st.slider("Pausa entre frases (segundos)", 0.0, 2.0, 0.25, 0.05)
        clause_pause = st.slider("Pausa entre orações (segundos)", 0.0, 1.0, 0.1, 0.05)
        st.caption("As pausas seguem a pontuação reconhecida pela voz. A divisão de trechos pode acrescentar intervalos.")
    audio_settings = {"pitch": pitch, "volume_db": volume_db,
                      "sentence_pause": sentence_pause, "clause_pause": clause_pause}
    language = st.selectbox("Idioma para a leitura de fórmulas", ["Português brasileiro", "English", "Español"])
    st.caption("O idioma dos parágrafos é preservado.")
    # Capture the previous unkeyed editor once so existing sessions retain their glossary.
    if "pronunciation_config" not in st.session_state:
        legacy_editor = st.empty()
        previous_glossary = legacy_editor.text_area("Pronúncias científicas", placeholder="ATP = a tê pê\nNaCl = cloreto de sódio",
                                                    help="Uma entrada por linha: termo = pronúncia. Aplicado ao texto antes da revisão.")
        st.session_state["pronunciation_config"] = previous_glossary
        legacy_editor.empty()
    with st.expander("Importar configuração de pronúncias"):
        pronunciation_file = st.file_uploader("Arquivo de pronúncias", type=["txt", "conf"], key="pronunciation-file",
                                              help="Até 5 MB. Uma entrada por linha: termo = pronúncia. Linhas iniciadas com # são comentários.")
        import_behavior = st.radio("Como importar", ["Mesclar com as atuais", "Substituir todas"], key="pronunciation-import-behavior",
                                   help="Ao mesclar, a pronúncia do arquivo prevalece para termos repetidos.")
        if st.button("Importar pronúncias", disabled=pronunciation_file is None):
            try:
                updated_glossary = import_pronunciations(pronunciation_file.getvalue(),
                    st.session_state["pronunciation_config"], replace=import_behavior == "Substituir todas")
                st.session_state["pronunciation_config"] = updated_glossary
                st.success(f"Configuração carregada: {len(parse_glossary(updated_glossary))} pronúncia(s).")
            except ValueError as exc:
                st.error(str(exc))
    glossary_raw = st.text_area("Pronúncias científicas", key="pronunciation_config",
                               placeholder="ATP = a tê pê\nNaCl = cloreto de sódio",
                               help="Uma entrada por linha: termo = pronúncia. Aplicado ao texto antes da revisão.")
    try:
        glossary_for_download = parse_glossary(glossary_raw)
    except ValueError as exc:
        st.error(str(exc))
        glossary_for_download = {}
    configuration_text = "\n".join(f"{term} = {pronunciation}" for term, pronunciation in glossary_for_download.items())
    st.download_button("Baixar configuração de pronúncias", configuration_text.encode("utf-8"),
                       "pronuncias.txt", mime="text/plain", disabled=not glossary_for_download)
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
        docling_container = st.text_input("Container Docling", os.getenv("DOCLING_CONTAINER", ""),
                                          help="Vazio: usa Docling instalado no Python local.")
        formula_enrichment = st.checkbox("Reconhecer fórmulas no Docling", value=True)
        st.caption("O primeiro uso pode baixar os modelos gratuitos do Docling. Depois, a extração roda localmente.")

    with st.expander("Ouvir uma prévia da voz", expanded=True):
        preview_text = st.text_area("Texto da prévia", "A energia é igual à massa vezes a velocidade da luz ao quadrado.",
                                    max_chars=500, height=100)
        preview_key = signature([preview_text, glossary_raw, voice, voice_lang, speed, audio_settings])
        if st.button("Gerar prévia da voz", disabled=not ready_voice or not preview_text.strip()):
            try:
                preview_narration = apply_glossary(preview_text, parse_glossary(glossary_raw))
                with st.spinner("Preparando prévia…"):
                    with tempfile.TemporaryDirectory(prefix="ciencia-voz-previa-") as temporary:
                        preview_path = Path(temporary) / "previa.mp3"
                        synthesize_kokoro(kokoro_engine(str(models_dir.resolve())), preview_narration,
                                          preview_path, voice, speed, voice_lang, **audio_settings)
                        st.session_state["voice_preview"] = (preview_key, preview_path.read_bytes())
            except Exception as exc:
                st.error(friendly_error(exc))
        preview = st.session_state.get("voice_preview")
        if preview and preview[0] == preview_key:
            st.audio(preview[1], format="audio/mpeg")
        elif preview:
            st.caption("Gere outra prévia para ouvir os ajustes atuais.")

def render_track_voice(key):
    # Keep overrides independently of widget cleanup when switching input modes.
    saved = st.session_state.setdefault("track_voice_overrides", {}).setdefault(key, {})
    default = "Usar padrão da sidebar"
    language_key = "track-language-" + key
    if language_key not in st.session_state:
        st.session_state[language_key] = saved.get("language", default)
    left, right = st.columns(2)
    chosen = left.selectbox("Idioma deste áudio", [default, *VOICE_OPTIONS], key=language_key,
                            help="O padrão acompanha a sidebar. Uma escolha específica vale somente para este áudio e não traduz o texto.")
    saved["language"] = chosen
    effective_language = voice_language if chosen == default else chosen
    voice_key = "track-voice-" + key + "-" + effective_language
    if voice_key not in st.session_state:
        st.session_state[voice_key] = saved.get("voices", {}).get(effective_language, default)
    chosen_voice = right.selectbox("Voz deste áudio", [default, *VOICE_OPTIONS[effective_language]], key=voice_key,
                                  help="Mostra apenas vozes compatíveis com o idioma deste áudio.")
    saved.setdefault("voices", {})[effective_language] = chosen_voice
    effective_voice = chosen_voice if chosen_voice != default else (
        voice if effective_language == voice_language else VOICE_OPTIONS[effective_language][0])
    st.caption(f"Este áudio: {effective_language} · {effective_voice}")
    return effective_language, effective_voice


def render_audio_export(tracks, review_key, *, use_ai=False, source_hash="", package_prefix="", stage=4):
    settings_key = signature([review_key, voice, speed, voice_language, audio_settings,
                              [[t.language, t.voice] for t in tracks]])
    chars = sum(len(t.text) for t in tracks)
    minutes = round(sum(len(t.text.split()) for t in tracks) / (140 * speed))
    requests = sum(len(chunk_text(t.text, limit=700)) for t in tracks)
    st.caption(f"{chars:,} caracteres · {requests} trecho(s) de voz local · duração aproximada: {max(1, minutes)} min.")
    reviewed = st.checkbox("Revisei o texto, as fórmulas e as pronúncias", key="review-" + review_key)

    st.subheader(f"{stage} · Gere e baixe seus áudios")
    st.caption("Voz gerada por inteligência artificial. Os MP3 e as transcrições serão salvos em uma pasta própria para esta geração.")
    if not ready_voice:
        st.info("Baixe os arquivos de voz Kokoro na barra lateral para gerar MP3 sem serviços pagos.")
    if st.button("Gerar arquivos MP3", type="primary", disabled=not (reviewed and ready_voice and all(t.text.strip() and t.title.strip() for t in tracks))):
        bar = st.progress(0, text="Gerando áudio…")
        try:
            root = Path(os.getenv("AUDIO_OUTPUT_DIR", "audios"))
            if not root.is_absolute():
                root = BASE / root
            engine = kokoro_engine(str(models_dir.resolve()))
            folder = export_tracks(None, tracks, root, voice=voice, speed=speed,
                                   model="kokoro-82m-onnx-v1.0", language=voice_language,
                                   track_synthesizer=lambda track, text, path: synthesize_kokoro(
                                       engine, text, path, track.voice, speed, VOICE_LANGUAGES[track.language], **audio_settings),
                                   audio_settings=audio_settings,
                                   metadata={"engine": "ollama" if use_ai else "manual", "model": ollama_model if use_ai else None},
                                   source_hash=source_hash,
                                   progress=lambda n, total: bar.progress(n / total, text=f"Áudio: trecho {n} de {total}"))
            st.session_state[package_prefix + "package"] = str(folder)
            st.session_state[package_prefix + "package_settings"] = settings_key
        except Exception as exc:
            logging.getLogger("ciencia_voz").exception("Falha na geração de arquivos MP3")
            st.error(friendly_error(exc))
            with st.expander("Detalhes do erro de geração"):
                st.code(f"{type(exc).__name__}: {exc}", language="text")
        finally:
            bar.empty()

    package = st.session_state.get(package_prefix + "package")
    if package:
        folder = Path(package)
        if st.session_state.get(package_prefix + "package_settings") != settings_key:
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


st.title("Ciência em Voz")
st.markdown("Transforme os capítulos que importam em uma biblioteca de áudio.")
st.caption("Escolha um PDF ou reutilize textos prontos para montar sua biblioteca de áudio.")

input_mode = st.radio("Origem do conteúdo", ["PDF", "Textos e arquivos TXT"], horizontal=True)
returning_to_pdf = input_mode == "PDF" and st.session_state.get("previous_input_mode") == "Textos e arquivos TXT"
st.session_state["previous_input_mode"] = input_mode
if input_mode == "Textos e arquivos TXT":
    st.subheader("1 · Adicione seus textos")
    st.caption("Recupere transcrições salvas ou cole um texto pronto. Cada texto será um arquivo MP3.")
    items = st.session_state.setdefault("text_items", [])
    with st.expander("Colar um texto", expanded=True):
        with st.form("paste-text", clear_on_submit=True):
            title = st.text_input("Título do áudio")
            pasted = st.text_area("Cole o texto", height=180,
                                  placeholder="Cole aqui a transcrição que deseja ouvir…")
            if st.form_submit_button("Adicionar texto", type="primary"):
                if not title.strip() or not pasted.strip():
                    st.error("Informe um título e um texto antes de adicionar.")
                else:
                    items.append({"id": uuid.uuid4().hex, "title": title.strip(),
                                  "text": pasted.strip(), "selected": True})
                    st.success("Texto adicionado à lista de narração.")
    with st.expander("Importar arquivos TXT", expanded=True):
        uploads = st.file_uploader("Selecione um ou mais arquivos TXT", type=["txt"], accept_multiple_files=True,
                                   key="text-imports", help="Até 5 MB por arquivo. UTF-8, UTF-16 com BOM ou Windows-1252.")
        if st.button("Adicionar arquivos TXT", disabled=not uploads):
            try:
                imported = [{"id": uuid.uuid4().hex, "title": Path(f.name).stem,
                             "text": decode_txt(f.getvalue()), "selected": True} for f in uploads]
                items.extend(imported)
                st.success(f"{len(imported)} texto(s) importado(s). Confira os títulos e o conteúdo abaixo.")
            except ValueError as exc:
                st.error(str(exc))
    if not items:
        st.info("Cole um texto ou importe suas transcrições TXT para começar.")
        st.stop()
    st.subheader("2 · Selecione e revise os textos")
    mark, unmark = st.columns(2)
    action = True if mark.button("Marcar todos", key="texts-mark") else None
    if unmark.button("Desmarcar todos", key="texts-unmark"):
        action = False
    if action is not None:
        for item in items:
            item["selected"] = action
            st.session_state["text-selected-" + item["id"]] = action
    tracks = []
    for item in list(items):
        item_key = item["id"]
        with st.container(border=True):
            selected = st.checkbox("Incluir no áudio", value=item["selected"], key="text-selected-" + item_key)
            item["selected"] = selected
            with st.expander(item["title"], expanded=selected):
                item["title"] = st.text_input("Título", item["title"], key="text-title-" + item_key)
                track_language, track_voice = render_track_voice("text-" + item_key)
                edit_key = "text-content-" + item_key
                if st.button("Aplicar pronúncias do glossário", key="text-glossary-" + item_key):
                    try:
                        st.session_state[edit_key] = apply_glossary(st.session_state.get(edit_key, item["text"]),
                                                                  parse_glossary(glossary_raw))
                    except ValueError as exc:
                        st.error(str(exc))
                item["text"] = st.text_area("Texto que será narrado", item["text"], height=230, key=edit_key)
                st.download_button("Baixar transcrição", item["text"].encode("utf-8"),
                                   f"transcricao-{item_key[:8]}.txt", mime="text/plain", key="text-download-" + item_key)
                if st.button("Remover texto", key="text-remove-" + item_key):
                    items.remove(item)
                    st.rerun()
            if selected:
                tracks.append(Track(item["title"], item["text"], None, None, track_language, track_voice))
    st.caption(f"{len(tracks)} de {len(items)} texto(s) selecionado(s).")
    if not tracks:
        st.info("Selecione ao menos um texto para gerar áudio.")
        st.stop()
    if any(not t.title.strip() or not t.text.strip() for t in tracks):
        st.warning("Todas as seleções precisam de título e texto.")
    text_key = signature([[t.title, t.text] for t in tracks])
    render_audio_export(tracks, "text-" + text_key, source_hash=hashlib.sha256(
                        json.dumps([[t.title, t.text] for t in tracks], ensure_ascii=False).encode()).hexdigest(),
                        package_prefix="text_", stage=3)
    st.stop()

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

st.caption(f"Documento em uso: {name}")
password = st.text_input("Senha do PDF, se necessário", value=st.session_state.get("pdf_password", ""), type="password")
st.session_state["pdf_password"] = password
structure_options = ["Automático (sumário e títulos)", "Apenas títulos", "Por páginas"]
mode_label = st.radio("Como identificar a estrutura", structure_options,
                      index=structure_options.index(st.session_state.get("pdf_structure_mode", structure_options[0])), horizontal=True)
st.session_state["pdf_structure_mode"] = mode_label
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
mark, unmark, counter = st.columns([1, 1, 2])
selection_default_key = "selection-default-" + tree_key
selection_version_key = "selection-version-" + tree_key
selection_mask_key = "selection-mask-" + tree_key
selection_saved_key = "selection-saved-" + tree_key
if returning_to_pdf:
    st.session_state[selection_mask_key] = st.session_state.get(selection_saved_key, [])
    st.session_state[selection_version_key] = st.session_state.get(selection_version_key, 0) + 1
if mark.button("Marcar todos", key="pdf-mark"):
    st.session_state[selection_default_key] = True
    st.session_state.pop(selection_mask_key, None)
    st.session_state[selection_version_key] = st.session_state.get(selection_version_key, 0) + 1
if unmark.button("Desmarcar todos", key="pdf-unmark"):
    st.session_state[selection_default_key] = False
    st.session_state.pop(selection_mask_key, None)
    st.session_state[selection_version_key] = st.session_state.get(selection_version_key, 0) + 1
counter.caption(f"{len(sections)} capítulos, seções e seleções disponíveis")
selection_version = st.session_state.get(selection_version_key, 0)
editor_key = "tree-" + tree_key + (f"-{selection_version}" if selection_version else "")
rows = []
for section in sections:
    first, last = doc.page_range(section)
    mask = st.session_state.get(selection_mask_key)
    included = section.id in mask if mask is not None else st.session_state.get(selection_default_key, False)
    rows.append({"Ouvir": included, "Conteúdo": "　" * (section.level - 1) + section.title,
                 "Nível": section.level, "Páginas": f"{first}–{last}", "Origem": section.source})
edited = st.data_editor(rows, key=editor_key, hide_index=True, width="stretch",
                        disabled=["Conteúdo", "Nível", "Páginas", "Origem"],
                        column_config={"Ouvir": st.column_config.CheckboxColumn("Ouvir", width="small")})
st.session_state[selection_saved_key] = [s.id for s, row in zip(sections, edited) if row["Ouvir"]]
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
preparation_options = ["Leitura científica com Ollama", "Texto local, com revisão manual"]
prep_mode = st.radio("Preparação", preparation_options,
                     index=preparation_options.index(st.session_state.get("pdf_preparation_mode", preparation_options[0])), horizontal=True)
st.session_state["pdf_preparation_mode"] = prep_mode
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
        narration_key = f"narration-{prep_key}-{revision}-{i}"
        track_language, track_voice = render_track_voice(narration_key)
        with st.expander("Importar uma transcrição TXT para esta seleção"):
            transcript_file = st.file_uploader("Arquivo TXT da seleção", type=["txt"], key="import-" + narration_key,
                                               help="Substitui o texto desta seleção somente ao clicar no botão. Até 5 MB.")
            if st.button("Usar TXT nesta seleção", key="apply-" + narration_key, disabled=transcript_file is None):
                try:
                    st.session_state[narration_key] = decode_txt(transcript_file.getvalue())
                    st.success("Transcrição importada. Revise o texto abaixo.")
                except ValueError as exc:
                    st.error(str(exc))
        text = st.text_area("Texto que será narrado", prepared["text"], height=230,
                            key=narration_key, help="Edite ou cole uma transcrição pronta aqui.")
        prepared["text"] = text
        tracks.append(Track(prepared["title"], text, prepared["first_page"], prepared["last_page"],
                            track_language, track_voice))
        st.download_button("Baixar transcrição", text.encode("utf-8"), f"transcricao-{i + 1:03d}.txt",
                           mime="text/plain", key=f"txt-{i}")

render_audio_export(tracks, signature([prep_key, [t.text for t in tracks]]),
                    use_ai=use_ai, source_hash=hashlib.sha256(data).hexdigest())
