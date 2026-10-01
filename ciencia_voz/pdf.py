from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import re
import unicodedata

import pymupdf


@dataclass
class Line:
    page: int  # 0-based physical PDF page, never printed page numbers
    text: str
    bbox: tuple[float, float, float, float]
    size: float = 11
    bold: bool = False
    level: int = 0


@dataclass
class Section:
    id: str
    title: str
    level: int
    start: int  # inclusive global line index
    end: int  # exclusive; includes descendants
    source: str


@dataclass
class Document:
    lines: list[Line]
    sections: list[Section]
    pages: int
    warnings: list[str] = field(default_factory=list)
    scanned_pages: list[int] = field(default_factory=list)

    def text(self, section: Section) -> str:
        return "\n".join(x.text for x in self.lines[section.start:section.end])

    def page_range(self, section: Section) -> tuple[int, int]:
        part = self.lines[section.start:section.end]
        return part[0].page + 1, part[-1].page + 1


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).casefold()
    return re.sub(r"[^a-z0-9]", "", text)


def make_sections(headings: list[tuple[int, str, int, str]], total: int) -> list[Section]:
    """A parent's interval ends at the next heading of equal or shallower depth."""
    unique = {}
    for start, title, level, source in headings:
        if 0 <= start < total:
            unique.setdefault(start, (start, title, max(1, min(int(level), 6)), source))
    ordered = sorted(unique.values())
    result = []
    for i, (start, title, level, source) in enumerate(ordered):
        end = next((h[0] for h in ordered[i + 1:] if h[2] <= level), total)
        result.append(Section(f"s-{start}-{i}", title, level, start, end, source))
    if result and result[0].start > 0:
        result.insert(0, Section("s-opening", "Texto inicial / resumo", 1, 0,
                                 result[0].start, "automático"))
    return result


def page_sections(lines: list[Line], pages: int) -> list[Section]:
    return [Section(f"p-{p}", f"Página {p + 1}", 1,
                    next(i for i, line in enumerate(lines) if line.page == p),
                    next((i for i, line in enumerate(lines) if line.page > p), len(lines)),
                    "páginas") for p in range(pages)]


def _heuristic_headings(lines: list[Line]) -> list[tuple[int, str, int, str]]:
    sizes = Counter(round(x.size, 1) for x in lines for _ in range(min(len(x.text), 200)))
    body = sizes.most_common(1)[0][0] if sizes else 11
    larger = sorted({round(x.size, 1) for x in lines if x.size > body * 1.13}, reverse=True)
    known = {"abstract", "resumo", "introducao", "introduction", "metodologia", "methods",
             "metodos", "resultados", "results", "discussao", "discussion", "conclusao",
             "conclusions", "conclusion", "referencias", "references", "bibliografia"}
    headings = []
    for i, line in enumerate(lines):
        t = line.text.strip()
        if not t or len(t) > 170 or re.search(r"\.{3,}|….*\d$", t):
            continue
        numbered = re.match(r"^(\d+(?:\.\d+)*)(?:\.?\s+)\S", t)
        chapter = re.match(r"^(cap[ií]tulo|chapter|parte|part)\s+[\divxlc]+\b", t, re.I)
        if line.level:
            level = line.level
        elif chapter:
            level = 1
        elif numbered and (line.bold or line.size >= body * 1.12):
            level = numbered.group(1).count(".") + 1
        elif normalized(t) in known:
            level = 1
        elif line.size > body * 1.13 and len(t.split()) < 22:
            # Standalone equations are not chapter headings.
            if re.search(r"[=∫∑√\\]|\$", t):
                continue
            level = larger.index(round(line.size, 1)) + 1
        else:
            continue
        headings.append((i, t, level, "títulos detectados"))
    return headings


def analyze(data: bytes, password: str = "", mode: str = "auto") -> Document:
    if len(data) > 50 * 1024 * 1024:
        raise ValueError("Envie um PDF de até 50 MB.")
    try:
        pdf = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError("O arquivo não é um PDF válido ou está danificado.") from exc
    with pdf:
        if pdf.needs_pass and not pdf.authenticate(password):
            raise ValueError("PDF protegido. Informe a senha correta.")
        if not 0 < len(pdf) <= 500:
            raise ValueError("O PDF deve ter entre 1 e 500 páginas.")
        lines, scanned, warnings = [], [], []
        multicolumn = False
        for p, page in enumerate(pdf):
            page_lines = []
            blocks = page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES,
                                   sort=True)["blocks"]
            for block in blocks:
                for line in block.get("lines", []):
                    spans = line["spans"]
                    text = "".join(s["text"] for s in spans).strip()
                    if text:
                        page_lines.append(Line(p, text, tuple(line["bbox"]),
                                               max(s["size"] for s in spans),
                                               any(s["flags"] & 16 for s in spans)))
            left = [x for x in page_lines if x.bbox[0] < page.rect.width * .4
                    and x.bbox[2] < page.rect.width * .59]
            right = [x for x in page_lines if x.bbox[0] > page.rect.width * .44]
            if len(left) >= 5 and len(right) >= 5:
                multicolumn = True
            if sum(len(x.text) for x in page_lines) < 40:
                scanned.append(p + 1)
            if not page_lines:
                page_lines = [Line(p, "[Página sem texto extraível: use leitura visual com IA.]",
                                   tuple(page.rect))]
            lines.extend(page_lines)
        # Remove only recurring edge text, not unique scientific content.
        edge_counts = Counter()
        for p, page in enumerate(pdf):
            edge_counts.update({normalized(x.text) for x in lines if x.page == p
                                and (x.bbox[1] < 35 or x.bbox[3] > page.rect.height - 30)})
        repeated = {t for t, n in edge_counts.items() if n >= max(3, len(pdf) * .5)}
        filtered = [x for x in lines if normalized(x.text) not in repeated or
                    not (x.bbox[1] < 35 or x.bbox[3] > pdf[x.page].rect.height - 30)]
        # Keep a marker even if all text on a page was removed.
        for p, page in enumerate(pdf):
            if not any(x.page == p for x in filtered):
                filtered.append(Line(p, "[Página sem texto extraível.]", tuple(page.rect)))
        lines = sorted(filtered, key=lambda x: x.page)
        toc = pdf.get_toc(simple=False)
        headings = []
        if mode == "auto" and toc:
            for entry in toc:
                level, title, page_number = entry[:3]
                if not 1 <= page_number <= len(pdf):
                    continue  # External/non-page bookmarks are not content.
                candidates = [(i, x) for i, x in enumerate(lines) if x.page == page_number - 1]
                matches = [(i, x) for i, x in candidates if normalized(title) == normalized(x.text)]
                if matches:
                    start = matches[0][0]
                else:
                    point = entry[3].get("to") if len(entry) > 3 else None
                    if point is not None and point.y > 0:
                        start = min(candidates, key=lambda pair: abs(pair[1].bbox[1] - point.y))[0]
                    else:
                        start = candidates[0][0]
                    warnings.append(f'Marcador "{title}": limite aproximado; confira a seleção.')
                headings.append((start, title, level, "marcadores do PDF"))
            if headings != sorted(headings, key=lambda h: h[0]):
                warnings.append("Marcadores fora de ordem foram reorganizados pelas páginas.")
        if not headings and mode != "pages":
            headings = _heuristic_headings(lines)
            if headings:
                warnings.append("Estrutura inferida pela tipografia. Confira os títulos e os limites.")
        sections = make_sections(headings, len(lines)) if headings else page_sections(lines, len(pdf))
        if not headings:
            warnings.append("Nenhum título confiável foi encontrado. Selecione páginas ou use OCR visual.")
        if scanned:
            warnings.append("Páginas com pouco ou nenhum texto: " + ", ".join(map(str, scanned[:30])) +
                            ". Use OCR visual para recuperar texto e estrutura.")
        if multicolumn:
            warnings.append("Possível documento com várias colunas. Use OCR visual para reconstruir a ordem de leitura.")
        warnings.append("Fórmulas, tabelas e símbolos podem perder significado na extração local; revise a narração.")
        return Document(lines, sections, len(pdf), list(dict.fromkeys(warnings)), scanned)


def from_markdown(pages: list[str], base: Document) -> Document:
    """OCR output: explicit heading levels, retaining physical page attribution."""
    lines = []
    for p, text in enumerate(pages):
        for raw in text.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            heading = re.match(r"^(#{1,6})\s+(.+)$", raw)
            lines.append(Line(p, heading.group(2) if heading else raw, (0, 0, 0, 0),
                              level=len(heading.group(1)) if heading else 0))
        if not any(x.page == p for x in lines):
            lines.append(Line(p, "[Página sem conteúdo legível.]", (0, 0, 0, 0)))
    headings = [(i, x.text, x.level, "OCR visual com IA") for i, x in enumerate(lines) if x.level]
    sections = make_sections(headings, len(lines)) if headings else page_sections(lines, len(pages))
    return Document(lines, sections, len(pages),
                    ["Estrutura e texto extraídos com IA. Revise títulos, fórmulas e conteúdo ilegível."])


def custom_section(doc: Document, title: str, first: int, last: int) -> Section:
    if not title.strip() or not 1 <= first <= last <= doc.pages:
        raise ValueError("Informe um título e um intervalo válido de páginas.")
    start = next(i for i, x in enumerate(doc.lines) if x.page == first - 1)
    end = next((i for i, x in enumerate(doc.lines) if x.page >= last), len(doc.lines))
    return Section(f"manual-{first}-{last}-{normalized(title)}", title.strip(), 1, start, end, "manual")


def deduplicate(sections: list[Section]) -> tuple[list[Section], list[str]]:
    selected, skipped = [], []
    for section in sorted(sections, key=lambda x: (x.start, -x.end)):
        if any(s.start <= section.start and s.end >= section.end for s in selected):
            skipped.append(section.title)
        elif any(s.start < section.end and section.start < s.end for s in selected):
            raise ValueError("Há intervalos parcialmente sobrepostos. Ajuste a seleção para evitar áudio duplicado.")
        else:
            selected.append(section)
    return selected, skipped


def render_page(data: bytes, page: int, password: str = "") -> bytes:
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        if pdf.needs_pass and not pdf.authenticate(password):
            raise ValueError("Senha incorreta.")
        source = pdf[page]
        scale = min(2.5, 2400 / max(source.rect.width, source.rect.height))
        return source.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")
