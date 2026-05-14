"""Transcript preview + full-text extraction shared by orchestrator and local-transcribe worker."""
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET
from xml.parsers.expat import ExpatError

PREVIEW_CHARS = 200


def _read_docx_text(file_path: Path | str) -> str:
    try:
        with zipfile.ZipFile(file_path) as zf:
            xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
    except (OSError, zipfile.BadZipFile, ET.ParseError, ExpatError):
        return ""

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", ns):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
        joined = "".join(texts).strip()
        if joined:
            paragraphs.append(joined)
    return "\n".join(paragraphs)


def _read_body(file_path: Path | str) -> str:
    """Read a transcript markdown file and return the prose body only.

    Strips YAML frontmatter and leading '#'-headings + blank lines. Remaining
    lines are single-spaced into one string.
    """
    path = Path(file_path)
    if path.suffix.lower() == ".docx":
        return " ".join(line.strip() for line in _read_docx_text(path).splitlines() if line.strip())

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return ""

    lines = text.splitlines()
    i = 0
    # Skip YAML frontmatter
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        i += 1
    # Skip blank + heading lines
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
        i += 1

    return " ".join(line.strip() for line in lines[i:] if line.strip())


def extract_transcript_preview(file_path: Path | str, max_chars: int = PREVIEW_CHARS) -> str:
    """Return the first ~max_chars of the transcript body (for card previews)."""
    body = _read_body(file_path)
    if len(body) > max_chars:
        body = body[:max_chars].rstrip() + "…"
    return body


def extract_transcript_text(file_path: Path | str) -> str:
    """Return the full transcript body (for DB-backed search)."""
    return _read_body(file_path)
