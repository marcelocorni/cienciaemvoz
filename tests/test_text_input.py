import pytest

from ciencia_voz.text_input import decode_txt


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "cp1252"])
def test_saved_transcript_preserves_accents_and_paragraphs(encoding):
    text = "Etéreum: precisão e revocação.\r\n\r\nEnergia em joules."
    assert decode_txt(text.encode(encoding)) == text.replace("\r\n", "\n")


@pytest.mark.parametrize("content", [b"", b" \n ", b"binary\x00file", b"x" * (5 * 1024 * 1024 + 1)],
                         ids=["empty", "whitespace", "binary", "oversize"])
def test_invalid_upload_is_rejected(content):
    with pytest.raises(ValueError):
        decode_txt(content)



def test_pronunciation_import_merges_case_insensitively_and_can_replace():
    from ciencia_voz.text_input import import_pronunciations
    from ciencia_voz.science import parse_glossary, apply_glossary
    current = "ATP = leitura anterior\nEthereum = Etéreum"
    data = "# Minha configuração\natp = a tê pê\nROC-AUC = róqui áuqui".encode("utf-8-sig")
    merged = parse_glossary(import_pronunciations(data, current))
    assert len(merged) == 3
    assert apply_glossary("ATP e Ethereum", merged) == "a tê pê e Etéreum"
    assert parse_glossary(import_pronunciations(data, current, replace=True)) == {
        "atp": "a tê pê", "ROC-AUC": "róqui áuqui"}


@pytest.mark.parametrize("content", [b"# comments only", b"ATP = valid\nmissing separator"])
def test_pronunciation_configuration_is_validated_as_a_whole(content):
    from ciencia_voz.text_input import import_pronunciations
    with pytest.raises(ValueError):
        import_pronunciations(content, "Ethereum = Etéreum")



def test_last_duplicate_pronunciation_wins_even_when_spelling_changes():
    from ciencia_voz.text_input import import_pronunciations
    from ciencia_voz.science import parse_glossary
    data = "ATP = primeira\natp = segunda\nATP = a tê pê".encode("utf-8")
    assert parse_glossary(import_pronunciations(data)) == {"ATP": "a tê pê"}
