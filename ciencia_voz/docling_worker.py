"""Worker executável no Python local ou no container Docling já existente."""
import base64
import io
import json
import re
import sys


def convert(payload):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.types.io import DocumentStream

    options = PdfPipelineOptions()
    options.do_formula_enrichment = bool(payload.get("formulas", True))
    options.do_ocr = True
    options.enable_remote_services = False
    converter = DocumentConverter(format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=options)
    })
    result = converter.convert(DocumentStream(name="documento.pdf", stream=io.BytesIO(
        base64.b64decode(payload["pdf"]))), max_num_pages=500)
    if str(result.status.value) != "success":
        raise ValueError("Docling não concluiu a conversão integral do documento.")
    doc = result.document
    entries = []
    for item, depth in doc.iterate_items():
        label = item.label.value
        if label in {"page_header", "page_footer"} or not item.prov:
            continue
        if label == "table":
            text = item.export_to_markdown(doc=doc)
        else:
            text = getattr(item, "text", "")
        if not text.strip():
            continue
        if label == "formula":
            text = "$" + text.strip().strip("$") + "$"
        level = 0
        if label in {"section_header", "title"}:
            numbered = re.match(r"^(\d+(?:\.\d+)*)\.?\s", text)
            level = numbered.group(1).count(".") + 1 if numbered else max(1, getattr(item, "level", 1))
        entries.append({"page": item.prov[0].page_no, "text": text, "level": level})
    return {"entries": entries, "pages": len(doc.pages)}


if __name__ == "__main__":
    output = convert(json.load(sys.stdin))
    print("CIENCIA_VOZ_RESULT=" + json.dumps(output, ensure_ascii=False))
