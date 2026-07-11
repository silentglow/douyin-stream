"""extract_transcript_text must preserve paragraph breaks for in-app reading."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from media_tools.transcribe.preview import extract_transcript_preview, extract_transcript_text


def _write_minimal_docx(path: Path, paragraphs: list[str]) -> None:
    """Write a tiny valid docx with the given paragraph texts."""
    W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    document = Element(f"{{{W_NS}}}document")
    body = SubElement(document, f"{{{W_NS}}}body")
    for text in paragraphs:
        p = SubElement(body, f"{{{W_NS}}}p")
        r = SubElement(p, f"{{{W_NS}}}r")
        t = SubElement(r, f"{{{W_NS}}}t")
        t.text = text

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", tostring(document, encoding="utf-8", xml_declaration=True))


def test_extract_transcript_text_preserves_paragraphs(tmp_path: Path) -> None:
    docx = tmp_path / "sample.docx"
    _write_minimal_docx(
        docx,
        [
            "发言人1  00:00  第一段内容",
            "发言人1  00:12  第二段内容",
            "发言人2  00:30  第三段内容",
        ],
    )

    text = extract_transcript_text(docx)
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 3
    assert "第一段内容" in lines[0]
    assert "第二段内容" in lines[1]
    assert "第三段内容" in lines[2]

    # Preview may still collapse whitespace for card display, but must not be empty.
    preview = extract_transcript_preview(docx)
    assert "第一段内容" in preview
