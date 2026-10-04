"""Report export helpers for Markdown, PDF, and DOCX."""

from html import escape
from io import BytesIO
import os
import re
import unicodedata
import zipfile


TEXT_REPLACEMENTS = {
    "\u00a0": " ",
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u2022": "-",
    "\u2026": "...",
    "\u2190": "<-",
    "\u2191": "^",
    "\u2192": "->",
    "\u2193": "v",
    "\u21d2": "=>",
    "\u2713": "check",
    "\u2714": "check",
    "\u2717": "x",
    "\u00b7": "-",
    "\ufffd": "",
    "â€”": "-",
    "â€“": "-",
    "â€•": "-",
    "â€˜": "'",
    "â€™": "'",
    "â€œ": '"',
    "â€": '"',
    "â€¢": "-",
    "â€¦": "...",
    "â†’": "->",
    "â†": "<-",
    "âœ…": "check",
    "âœ“": "check",
    "ðŸš€": "",
    "ðŸ”¬": "",
}


def _clean_export_text(text: str) -> str:
    """Make generated text safe for PDF/DOCX fallback renderers."""
    cleaned = text or ""
    for source, replacement in TEXT_REPLACEMENTS.items():
        cleaned = cleaned.replace(source, replacement)

    cleaned = unicodedata.normalize("NFKD", cleaned)
    cleaned = cleaned.encode("ascii", errors="ignore").decode("ascii")
    cleaned = re.sub(r"(?<=\w)\s+\?\s+(?=\w)", " - ", cleaned)
    cleaned = re.sub(r"^\?\s+", "- ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def _markdown_to_html(markdown_text: str) -> str:
    try:
        import markdown

        body = markdown.markdown(
            markdown_text,
            extensions=["extra", "sane_lists", "tables"],
            output_format="html5",
        )
    except ImportError:
        body = "<pre>" + escape(markdown_text) + "</pre>"

    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <style>
          body {{ font-family: Arial, sans-serif; line-height: 1.55; color: #243c32; font-size: 11pt; }}
          h1, h2, h3 {{ color: #255b45; break-after: avoid; }}
          a {{ color: #255b45; }}
          pre {{ white-space: pre-wrap; overflow-wrap: anywhere; padding: 14px; background: #f3f5f0; }} table {{ border-collapse: collapse; width: 100%; }} th, td {{ padding: 8px; border: 1px solid #d9e2da; }} th {{ background: #e4eee5; }} @page {{ margin: 22mm; @bottom-right {{ content: "Page " counter(page); }} }}
        </style>
      </head>
      <body>{body}</body>
    </html>
    """


def export_markdown(report: str) -> tuple[bytes, str]:
    return report.encode("utf-8"), "text/markdown; charset=utf-8"


def export_pdf(report: str) -> tuple[bytes, str]:
    if os.getenv("PDF_RENDERER", "simple").lower() != "weasyprint":
        return _export_simple_pdf(report), "application/pdf"

    try:
        from weasyprint import HTML

        pdf_bytes = HTML(string=_markdown_to_html(report)).write_pdf()
        return pdf_bytes, "application/pdf"
    except Exception:
        return _export_simple_pdf(report), "application/pdf"


def export_docx(report: str) -> tuple[bytes, str]:
    return _export_simple_docx(report), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _plain_lines(markdown_text: str) -> list[str]:
    lines = []
    for line in markdown_text.splitlines():
        stripped = _clean_export_text(line.strip())
        stripped = re.sub(r"^#{1,6}\s+", "", stripped)
        stripped = re.sub(r"^\s*[-*]\s+", "- ", stripped)
        stripped = re.sub(r"\*\*(.*?)\*\*", r"\1", stripped)
        stripped = re.sub(r"\*(.*?)\*", r"\1", stripped)
        stripped = re.sub(r"`([^`]*)`", r"\1", stripped)
        stripped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", stripped)
        lines.append(stripped)
    return lines or ["Research Report"]


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_line(line: str, limit: int = 88) -> list[str]:
    if len(line) <= limit:
        return [line]

    words = line.split()
    wrapped = []
    current = ""
    for word in words:
        next_line = f"{current} {word}".strip()
        if len(next_line) > limit and current:
            wrapped.append(current)
            current = word
        else:
            current = next_line
    if current:
        wrapped.append(current)
    return wrapped


def _markdown_blocks(markdown_text: str) -> list[tuple[str, str]]:
    blocks = []
    for raw_line in markdown_text.splitlines():
        line = _clean_export_text(raw_line.strip())
        if not line:
            blocks.append(("space", ""))
            continue

        kind = "body"
        text = line
        if line.startswith("# "):
            kind = "title"
            text = line[2:].strip()
        elif line.startswith("## "):
            kind = "h2"
            text = line[3:].strip()
        elif line.startswith("### "):
            kind = "h3"
            text = line[4:].strip()
        elif line.startswith(("- ", "* ")):
            kind = "bullet"
            text = line[2:].strip()
        elif re.match(r"^\d+\.\s+", line):
            kind = "number"

        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"\*(.*?)\*", r"\1", text)
        text = re.sub(r"`([^`]*)`", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
        blocks.append((kind, text))
    return blocks or [("title", "Research Report")]


def _chunk_pdf_pages(blocks: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    import textwrap

    pages, current, used = [], [], 0
    for kind, text in blocks:
        size = {"title": 21, "h2": 14, "h3": 11}.get(kind, 10)
        # A conservative width accommodates wide glyphs and unbroken URLs.
        limit = {"title": 36, "h2": 55, "h3": 70}.get(kind, 82)
        wrapped = textwrap.wrap(text, width=limit, break_long_words=True, break_on_hyphens=False) or [""]
        height = {"title": 30, "h2": 24, "h3": 19, "space": 8}.get(kind, 15)
        if kind in ("title", "h2", "h3") and used + height + 30 > 610 and current:
            pages.append(current)
            current, used = [], 0
        for line in wrapped:
            if used + height > 610 and current:
                pages.append(current)
                current, used = [], 0
            current.append((kind, line))
            used += height
    if current:
        pages.append(current)
    return pages or [[("title", "Research Report")]]


def _pdf_text(text: str, x: int, y: int, font: str = "F1", size: int = 10, color: str = "0.12 0.16 0.24 rg") -> str:
    return f"BT {color} /{font} {size} Tf {x} {y} Td ({_pdf_escape(text)}) Tj ET"


def _pdf_page_stream(page: list[tuple[str, str]], page_number: int, total_pages: int) -> bytes:
    commands = [
        "1 1 1 rg 0 0 612 792 re f",
        _pdf_text("ResearchAgent", 48, 758, "F2", 11, "0.15 0.36 0.27 rg"),
        _pdf_text("RESEARCH REPORT", 440, 758, "F1", 8, "0.40 0.45 0.42 rg"),
        "0.15 0.36 0.27 rg 48 742 516 2 re f",
    ]
    y = 711
    for kind, text in page:
        if kind == "space":
            y -= 8
            continue
        size = {"title": 21, "h2": 14, "h3": 11}.get(kind, 10)
        height = {"title": 30, "h2": 24, "h3": 19}.get(kind, 15)
        color = "0.15 0.36 0.27 rg" if kind in ("h2", "h3") else "0.14 0.20 0.17 rg"
        x = 60 if kind in ("bullet", "number") else 48
        if kind == "bullet":
            text = "- " + text
        commands.append(_pdf_text(text, x, y, "F2" if kind in ("title", "h2", "h3") else "F1", size, color))
        y -= height
    commands.extend([
        "0.84 0.87 0.84 rg 48 58 516 1 re f",
        _pdf_text("ResearchAgent | Review the cited sources before sharing.", 48, 39, "F1", 8, "0.40 0.45 0.42 rg"),
        _pdf_text(f"{page_number} / {total_pages}", 515, 39, "F1", 8, "0.40 0.45 0.42 rg"),
    ])
    return "\n".join(commands).encode("latin-1", errors="replace")


def _export_simple_pdf(report: str) -> bytes:
    pages = _chunk_pdf_pages(_markdown_blocks(report))
    streams = [
        _pdf_page_stream(page, index + 1, len(pages))
        for index, page in enumerate(pages)
    ]

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]

    page_object_numbers = []
    for stream in streams:
        content_number = len(objects) + 2
        page_number = len(objects) + 1
        page_object_numbers.append(page_number)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_number} 0 R >>".encode()
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
            + stream + b"\nendstream"
        )

    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>".encode()

    output = BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{index} 0 obj\n".encode())
        output.write(obj)
        output.write(b"\nendobj\n")

    xref_at = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode())
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n".encode()
    )
    return output.getvalue()


def _xml_escape(text: str) -> str:
    return escape(text, quote=True)


def _paragraph_xml(line: str) -> str:
    style = '<w:pPr><w:pStyle w:val="BodyText"/><w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr>'
    line = _clean_export_text(line)
    text = line
    if line.startswith("# "):
        style = '<w:pPr><w:pStyle w:val="Title"/></w:pPr>'
        text = line[2:].strip()
    elif line.startswith("## "):
        style = '<w:pPr><w:pStyle w:val="Heading2"/></w:pPr>'
        text = line[3:].strip()
    elif line.startswith("### "):
        style = '<w:pPr><w:pStyle w:val="Heading3"/></w:pPr>'
        text = line[4:].strip()
    elif line.startswith(("- ", "* ")):
        style = '<w:pPr><w:pStyle w:val="BodyText"/><w:ind w:left="360" w:hanging="180"/><w:spacing w:after="120"/></w:pPr>'
        text = "- " + line[2:].strip()

    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    return f"<w:p>{style}<w:r><w:t xml:space=\"preserve\">{_xml_escape(text)}</w:t></w:r></w:p>"


def _export_simple_docx(report: str) -> bytes:
    """Create an editable Word document without optional native dependencies."""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def runs(text, code=False):
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
        result = []
        for part in re.split(r"(\*\*.*?\*\*|\x60[^\x60]+\x60|\*[^*]+\*)", text):
            bold = part.startswith("**") and part.endswith("**")
            mono = code or (part.startswith(chr(96)) and part.endswith(chr(96)))
            italic = not bold and part.startswith("*") and part.endswith("*")
            value = part[2:-2] if bold else part[1:-1] if italic or (mono and not code) else part
            props = ("<w:b/>" if bold else "") + ("<w:i/>" if italic else "")
            if mono:
                props += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="18"/>'
            result.append(f'<w:r><w:rPr>{props}</w:rPr><w:t xml:space="preserve">{escape(value)}</w:t></w:r>')
        return "".join(result)

    def paragraph(text, style="Normal", code=False):
        return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{runs(text, code)}</w:p>'

    lines = report.splitlines()
    body, index, fenced = [], 0, False
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            fenced = not fenced
            if fenced and "mermaid" in stripped.lower():
                body.append(paragraph("Diagram definition (editable source)", "Caption"))
            index += 1
            continue
        if fenced:
            body.append(paragraph(line, "Code", True))
        elif "|" in stripped and index + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1]):
            rows = [stripped]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(lines[index])
                index += 1
            cells = [[c.strip() for c in row.strip().strip("|").split("|")] for row in rows]
            width = max(len(row) for row in cells)
            table = '<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>' + "".join(f'<w:{edge} w:val="single" w:sz="4" w:color="D9E2DA"/>' for edge in ("top", "left", "bottom", "right", "insideH", "insideV")) + '</w:tblBorders></w:tblPr>'
            for row_index, row in enumerate(cells):
                table += '<w:tr>' + ('<w:trPr><w:tblHeader/></w:trPr>' if row_index == 0 else '')
                for cell in row + [""] * (width - len(row)):
                    fill = "E4EEE5" if row_index == 0 else "FFFFFF"
                    table += f'<w:tc><w:tcPr><w:shd w:fill="{fill}"/></w:tcPr>{paragraph(cell, "TableText")}</w:tc>'
                table += '</w:tr>'
            body.append(table + '</w:tbl>')
            continue
        elif stripped:
            heading = re.match(r"^(#{1,6})\s+(.+)", stripped)
            if heading:
                body.append(paragraph(heading[2], f"Heading{min(len(heading[1]), 3)}"))
            elif re.match(r"^[-*+]\s+", stripped):
                body.append(paragraph("• " + stripped[2:], "ListText"))
            elif re.match(r"^\d+[.)]\s+", stripped):
                body.append(paragraph(stripped, "ListText"))
            elif stripped.startswith(">"):
                body.append(paragraph(stripped.lstrip("> "), "Quote"))
            elif re.fullmatch(r"[-*_]{3,}", stripped):
                body.append(paragraph(""))
            else:
                body.append(paragraph(stripped))
        index += 1

    def style(name, size, color="243C32", extra=""):
        return f'<w:style w:type="paragraph" w:styleId="{name}"><w:name w:val="{name}"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="160" w:line="290" w:lineRule="auto"/>{extra}</w:pPr><w:rPr><w:sz w:val="{size}"/><w:color w:val="{color}"/></w:rPr></w:style>'

    styles = f'<w:styles xmlns:w="{ns}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:spacing w:after="160" w:line="290" w:lineRule="auto"/><w:widowControl/></w:pPr></w:style>'
    for name, size in (("Heading1", 40), ("Heading2", 29), ("Heading3", 24)):
        level = int(name[-1]) - 1
        styles += style(name, size, "255B45", f'<w:keepNext/><w:keepLines/><w:outlineLvl w:val="{level}"/>')
    styles += style("ListText", 22, extra='<w:ind w:left="300" w:hanging="180"/>')
    styles += style("Code", 18, extra='<w:shd w:fill="F3F5F0"/>')
    styles += style("Quote", 22, "526457", '<w:ind w:left="300"/>')
    styles += style("Caption", 18, "657269")
    styles += style("TableText", 20)
    styles += '</w:styles>'
    relationships_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    office_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    document = f'<w:document xmlns:w="{ns}" xmlns:r="{office_ns}"><w:body>{"".join(body)}<w:sectPr><w:headerReference w:type="default" r:id="header"/><w:footerReference w:type="default" r:id="footer"/><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1200" w:bottom="1200" w:left="1200" w:right="1200" w:header="500" w:footer="500"/></w:sectPr></w:body></w:document>'
    types = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
    for part, kind in (("document", "document.main"), ("styles", "styles"), ("header", "header"), ("footer", "footer")):
        types += f'<Override PartName="/word/{part}.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml"/>'
    types += '</Types>'
    rels = f'<Relationships xmlns="{relationships_ns}">' + "".join(f'<Relationship Id="{part}" Type="{office_ns}/{part}" Target="{part}.xml"/>' for part in ("styles", "header", "footer")) + '</Relationships>'
    header = f'<w:hdr xmlns:w="{ns}">{paragraph("ResearchAgent  /  RESEARCH REPORT", "Caption")}</w:hdr>'
    footer = f'<w:ftr xmlns:w="{ns}"><w:p><w:pPr><w:jc w:val="right"/></w:pPr>{runs("ResearchAgent  •  Page ")}<w:fldSimple w:instr="PAGE"/></w:p></w:ftr>'
    files = {"[Content_Types].xml": types, "_rels/.rels": f'<Relationships xmlns="{relationships_ns}"><Relationship Id="document" Type="{office_ns}/officeDocument" Target="word/document.xml"/></Relationships>', "word/document.xml": document, "word/styles.xml": styles, "word/_rels/document.xml.rels": rels, "word/header.xml": header, "word/footer.xml": footer}
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, xml in files.items():
            archive.writestr(name, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + xml)
    return buffer.getvalue()


def export_report(report: str, export_format: str) -> tuple[bytes, str, str]:
    export_format = export_format.lower()
    exporters = {
        "md": export_markdown,
        "markdown": export_markdown,
        "pdf": export_pdf,
        "docx": export_docx,
    }
    if export_format not in exporters:
        raise ValueError("Unsupported export format. Use md, pdf, or docx.")

    data, media_type = exporters[export_format](report)
    extension = "md" if export_format == "markdown" else export_format
    return data, media_type, extension
