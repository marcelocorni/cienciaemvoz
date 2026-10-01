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
    assert "1 Introducao" not in narration.value
    assert next(b for b in app.button if b.label == "Gerar arquivos MP3").disabled
