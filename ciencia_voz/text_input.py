"""Importação conservadora de transcrições, sem alterar sua narração."""


def decode_txt(data: bytes) -> str:
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("Cada arquivo TXT deve ter até 5 MB.")
    try:
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            text = data.decode("utf-16")
        else:
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = data.decode("cp1252")
    except UnicodeError as exc:
        raise ValueError("Não foi possível ler o TXT. Salve-o em UTF-8 e tente novamente.") from exc
    if any(ord(c) < 32 and c not in "\t\r\n" for c in text):
        raise ValueError("O arquivo contém dados binários. Importe um arquivo de texto TXT.")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("O arquivo TXT está vazio.")
    return text



def import_pronunciations(data: bytes, current: str = "", *, replace: bool = False) -> str:
    from .science import parse_glossary
    imported = parse_glossary(decode_txt(data))
    if not imported:
        raise ValueError("O arquivo não contém pronúncias. Use termo = pronúncia, uma entrada por linha.")
    existing = {} if replace else parse_glossary(current)
    # Case-insensitive identity agrees with the actual pronunciation replacement.
    merged = {}
    for term, pronunciation in [*existing.items(), *imported.items()]:
        merged[term.casefold()] = (term, pronunciation)
    return "\n".join(f"{term} = {pronunciation}" for term, pronunciation in merged.values())
