from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_app_demo_structure_and_local_review():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    app.run()
    assert not app.exception
    assert not any(w.label == "Chave da API OpenAI" for w in app.text_input)
    assert any(w.label == "Endereço do Ollama" for w in app.text_input)
    next(b for b in app.button if b.label == "Experimentar com um PDF de exemplo").click().run()
    next(b for b in app.button if b.label == "Identificar estrutura").click().run()
    assert not app.exception
    assert app.metric[0].value == "2"
    # The native editor's delta is how Streamlit records selection changes.
    editor_key = next(k for k in app.session_state if k.startswith("tree-"))
    app.session_state[editor_key] = {"edited_rows": {1: {"Ouvir": True}}, "added_rows": [], "deleted_rows": []}
    app.run()
    assert not app.exception
    next(r for r in app.radio if r.label == "Preparação").set_value("Texto local, com revisão manual")
    app.session_state[editor_key] = {"edited_rows": {1: {"Ouvir": True}}, "added_rows": [], "deleted_rows": []}
    app.run()
    next(b for b in app.button if b.label == "Preparar textos da seleção").click()
    app.session_state[editor_key] = {"edited_rows": {1: {"Ouvir": True}}, "added_rows": [], "deleted_rows": []}
    app.run()
    assert not app.exception
    narration = next(a for a in app.text_area if a.label == "Texto que será narrado")
    assert "E = m c^2" in narration.value
    next(s for s in app.selectbox if s.label == "Idioma deste áudio").set_value("English")
    app.session_state[editor_key] = {"edited_rows": {1: {"Ouvir": True}}, "added_rows": [], "deleted_rows": []}
    app.run()
    assert next(s for s in app.selectbox if s.label == "Voz deste áudio").options == [
        "Usar padrão da sidebar", "af_heart", "am_michael"]
    assert "1 Introducao" not in narration.value
    assert next(b for b in app.button if b.label == "Gerar arquivos MP3").disabled



def test_voice_preview_uses_glossary_and_current_controls_without_pdf(monkeypatch):
    captured = []
    monkeypatch.setattr("ciencia_voz.local.kokoro_engine", lambda _: object())
    def synth(engine, text, path, voice, speed, lang, **settings):
        captured.append((text, voice, speed, lang, settings))
        path.write_bytes(b"MP3" * 100)
    monkeypatch.setattr("ciencia_voz.local.synthesize_kokoro", synth)
    monkeypatch.setattr(Path, "exists", lambda self: True if self.name in
                        {"kokoro-v1.0.onnx", "voices-v1.0.bin"} else original_exists(self))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    next(a for a in app.text_area if a.label == "Pronúncias científicas").set_value("ATP = a tê pê")
    next(a for a in app.text_area if a.label == "Texto da prévia").set_value("ATP.")
    next(a for a in app.slider if a.label == "Altura da voz (semitons)").set_value(-2.0)
    next(a for a in app.slider if a.label == "Volume (dB)").set_value(-3.0)
    next(b for b in app.button if b.label == "Gerar prévia da voz").click().run()
    assert not app.exception
    assert captured[0][0] == "a tê pê."
    assert captured[0][-1]["pitch"] == -2 and captured[0][-1]["volume_db"] == -3
    assert app.session_state["voice_preview"][1] == b"MP3" * 100
    next(a for a in app.slider if a.label == "Altura da voz (semitons)").set_value(1.0).run()
    assert any("Gere outra prévia" in c.value for c in app.caption)


original_exists = Path.exists


def test_mixed_track_languages_defaults_persistence_and_export(tmp_path, monkeypatch):
    import json
    captured = []
    monkeypatch.setenv("AUDIO_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr("ciencia_voz.local.kokoro_engine", lambda _: object())
    def synth(engine, text, path, voice, speed, lang, **settings):
        captured.append((text, voice, lang))
        path.write_bytes(b"MP3" * 100)
    monkeypatch.setattr("ciencia_voz.local.synthesize_kokoro", synth)
    monkeypatch.setattr("ciencia_voz.audio.join_mp3", lambda parts, dest: dest.write_bytes(b"MP3" * 100))
    monkeypatch.setattr(Path, "exists", lambda self: True if self.name in
                        {"kokoro-v1.0.onnx", "voices-v1.0.bin"} else original_exists(self))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    app.session_state["text_items"] = [
        {"id": "resumo", "title": "Resumo", "text": "Texto em português.", "selected": True},
        {"id": "abstract", "title": "Abstract", "text": "Scientific evidence. " * 80, "selected": True}]
    next(r for r in app.radio if r.label == "Origem do conteúdo").set_value("Textos e arquivos TXT").run()
    app.selectbox(key="track-language-text-abstract").set_value("English").run()
    app.selectbox(key="track-voice-text-abstract-English").set_value("am_michael").run()
    next(s for s in app.selectbox if s.label == "Voz Kokoro").set_value("pm_alex").run()
    assert any("Português brasileiro · pm_alex" in c.value for c in app.caption)
    next(r for r in app.radio if r.label == "Origem do conteúdo").set_value("PDF").run()
    next(r for r in app.radio if r.label == "Origem do conteúdo").set_value("Textos e arquivos TXT").run()
    assert app.selectbox(key="track-language-text-abstract").value == "English"
    assert app.selectbox(key="track-voice-text-abstract-English").value == "am_michael"
    next(c for c in app.checkbox if c.label == "Revisei o texto, as fórmulas e as pronúncias").check().run()
    next(b for b in app.button if b.label == "Gerar arquivos MP3").click().run()
    assert not app.exception
    assert captured[0] == ("Texto em português.", "pm_alex", "pt-br")
    assert len(captured) > 2  # Multiple synthesis blocks share the English override.
    assert all((v, lang) == ("am_michael", "en-us") for _, v, lang in captured[1:])
    assert " ".join(t for t, _, _ in captured[1:]) == ("Scientific evidence. " * 80).strip()
    manifest = json.loads((Path(app.session_state["text_package"]) / "manifesto.json").read_text(encoding="utf-8"))
    assert [(t["language"], t["voice"]) for t in manifest["tracks"]] == [
        ("Português brasileiro", "pm_alex"), ("English", "am_michael")]
    app.selectbox(key="track-language-text-abstract").set_value("Español").run()
    assert any("geração anterior" in w.value for w in app.warning)
    assert app.selectbox(key="track-voice-text-abstract-Español").options == [
        "Usar padrão da sidebar", "ef_dora", "em_alex"]
    app.selectbox(key="track-language-text-abstract").set_value("Usar padrão da sidebar").run()
    next(s for s in app.selectbox if s.label == "Idioma da voz").set_value("English").run()
    assert any("Este áudio: English · af_heart" in c.value for c in app.caption)



def test_select_all_can_be_reversed_after_individual_edits():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    next(b for b in app.button if b.label == "Experimentar com um PDF de exemplo").click().run()
    next(b for b in app.button if b.label == "Identificar estrutura").click().run()
    next(b for b in app.button if b.label == "Marcar todos").click().run()
    assert not app.exception
    assert app.dataframe[0].value["Ouvir"].all()
    editor_key = next(k for k in app.session_state if k.startswith("tree-") and k.endswith("-1"))
    app.session_state[editor_key] = {"edited_rows": {1: {"Ouvir": False}}, "added_rows": [], "deleted_rows": []}
    app.run()
    next(b for b in app.button if b.label == "Desmarcar todos").click().run()
    assert not app.exception
    assert not app.dataframe[0].value["Ouvir"].any()
    assert any("Marque os capítulos" in message.value for message in app.info)


def test_pasted_text_is_kept_when_switching_pdf_and_text_mode(monkeypatch):
    monkeypatch.setattr("ciencia_voz.local.narrate_ollama", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Ollama não deve ser chamado")))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    origin = lambda: next(r for r in app.radio if r.label == "Origem do conteúdo")
    origin().set_value("Textos e arquivos TXT").run()
    next(t for t in app.text_input if t.label == "Título do áudio").set_value("Resumo salvo")
    next(t for t in app.text_area if t.label == "Cole o texto").set_value("A energia é igual a m vezes c ao quadrado.")
    next(b for b in app.button if b.label == "Adicionar texto").click().run()
    assert not app.exception
    narration = next(t for t in app.text_area if t.label == "Texto que será narrado")
    narration.set_value("Transcrição já revisada.").run()
    origin().set_value("PDF").run()
    origin().set_value("Textos e arquivos TXT").run()
    assert next(t for t in app.text_area if t.label == "Texto que será narrado").value == "Transcrição já revisada."
    next(b for b in app.button if b.label == "Desmarcar todos").click().run()
    assert not app.exception
    assert not next(c for c in app.checkbox if c.label == "Incluir no áudio").value
    next(b for b in app.button if b.label == "Marcar todos").click().run()
    assert next(c for c in app.checkbox if c.label == "Incluir no áudio").value


def test_import_multiple_txt_then_export_without_pdf_or_ollama(tmp_path, monkeypatch):
    import io
    import json
    import streamlit as st
    real_uploader = st.file_uploader
    files = [io.BytesIO("Energia em joules.".encode("utf-8")), io.BytesIO("Precisão média.".encode("utf-16"))]
    files[0].name, files[1].name = "Resumo.txt", "Resultados.txt"
    monkeypatch.setattr(st, "file_uploader", lambda label, *a, **k: files if label == "Selecione um ou mais arquivos TXT" else real_uploader(label, *a, **k))
    monkeypatch.setenv("AUDIO_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr("ciencia_voz.local.kokoro_engine", lambda _: object())
    monkeypatch.setattr("ciencia_voz.local.narrate_ollama", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Ollama não deve ser chamado")))
    monkeypatch.setattr("ciencia_voz.local.synthesize_kokoro", lambda engine, text, path, *a, **k: path.write_bytes(b"MP3" * 100))
    monkeypatch.setattr(Path, "exists", lambda self: True if self.name in {"kokoro-v1.0.onnx", "voices-v1.0.bin"} else original_exists(self))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    next(r for r in app.radio if r.label == "Origem do conteúdo").set_value("Textos e arquivos TXT").run()
    next(b for b in app.button if b.label == "Adicionar arquivos TXT").click().run()
    assert not app.exception
    assert [t.value for t in app.text_input if t.label == "Título"] == ["Resumo", "Resultados"]
    next(c for c in app.checkbox if c.label == "Revisei o texto, as fórmulas e as pronúncias").check().run()
    next(b for b in app.button if b.label == "Gerar arquivos MP3").click().run()
    assert not app.exception
    folder = Path(app.session_state["text_package"])
    manifest = json.loads((folder / "manifesto.json").read_text(encoding="utf-8"))
    assert len(manifest["tracks"]) == 2
    assert all(t["first_page"] is None for t in manifest["tracks"])
    assert (folder / manifest["tracks"][1]["transcript"]).read_text(encoding="utf-8") == "Precisão média."
    assert "package" not in app.session_state



def test_import_txt_into_pdf_selection_and_keep_it_after_mode_switch(monkeypatch):
    import io
    import streamlit as st
    original_upload = st.file_uploader
    saved = io.BytesIO("Esta é uma transcrição já preparada pelo Ollama.".encode("utf-8-sig"))
    saved.name = "resumo.txt"
    monkeypatch.setattr(st, "file_uploader", lambda label, *a, **k: saved if label == "Arquivo TXT da seleção" else original_upload(label, *a, **k))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    next(b for b in app.button if b.label == "Experimentar com um PDF de exemplo").click().run()
    next(b for b in app.button if b.label == "Identificar estrutura").click().run()
    editor_key = next(k for k in app.session_state if k.startswith("tree-"))
    def select_section():
        app.session_state[editor_key] = {"edited_rows": {1: {"Ouvir": True}}, "added_rows": [], "deleted_rows": []}
    select_section()
    app.run()
    next(r for r in app.radio if r.label == "Preparação").set_value("Texto local, com revisão manual")
    select_section()
    app.run()
    next(b for b in app.button if b.label == "Preparar textos da seleção").click()
    select_section()
    app.run()
    next(b for b in app.button if b.label == "Usar TXT nesta seleção").click()
    select_section()
    app.run()
    assert not app.exception
    assert next(t for t in app.text_area if t.label == "Texto que será narrado").value == saved.getvalue().decode("utf-8-sig")
    next(r for r in app.radio if r.label == "Origem do conteúdo").set_value("Textos e arquivos TXT").run()
    next(r for r in app.radio if r.label == "Origem do conteúdo").set_value("PDF").run()
    assert not app.exception
    assert next(t for t in app.text_area if t.label == "Texto que será narrado").value == saved.getvalue().decode("utf-8-sig")



def test_pronunciation_file_import_preserves_existing_configuration_on_error(monkeypatch):
    import io
    import streamlit as st
    original_upload = st.file_uploader
    config = io.BytesIO("ATP = a tê pê\nROC-AUC = róqui áuqui".encode("utf-8-sig"))
    config.name = "pronuncias.txt"
    monkeypatch.setattr(st, "file_uploader", lambda label, *a, **k: config if label == "Arquivo de pronúncias" else original_upload(label, *a, **k))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    next(t for t in app.text_area if t.label == "Pronúncias científicas").set_value("Ethereum = Etéreum").run()
    next(b for b in app.button if b.label == "Importar pronúncias").click().run()
    assert not app.exception
    field = lambda: next(t for t in app.text_area if t.label == "Pronúncias científicas")
    assert "Ethereum = Etéreum" in field().value and "ROC-AUC = róqui áuqui" in field().value
    next(r for r in app.radio if r.label == "Como importar").set_value("Substituir todas")
    next(b for b in app.button if b.label == "Importar pronúncias").click().run()
    assert not app.exception and "Ethereum" not in field().value
    valid = field().value
    config.seek(0)
    config.truncate(0)
    config.write(b"invalid line")
    next(b for b in app.button if b.label == "Importar pronúncias").click().run()
    assert not app.exception
    assert field().value == valid
    assert any("Linha 1" in error.value for error in app.error)
