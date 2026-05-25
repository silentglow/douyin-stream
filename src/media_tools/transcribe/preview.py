from __future__ import annotations

"""Transcript preview + full-text extraction shared by orchestrator and local-transcribe worker."""
import logging
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET
from xml.parsers.expat import ExpatError

logger = logging.getLogger(__name__)

PREVIEW_CHARS = 200

# 用 flag 避免每次提取都重复警告"pypdf 没装"
_pypdf_warned = False


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


def _read_pdf_text(file_path: Path | str) -> str:
    """Extract text from PDF using pypdf。

    历史 bug：原来 try/except Exception 把 ImportError 也吞了，pypdf 未安装时
    静默返回空字符串 → 用户在 UI 看到"读取不了"。现在显式区分。
    """
    global _pypdf_warned
    try:
        from pypdf import PdfReader
    except ImportError:
        if not _pypdf_warned:
            logger.warning(
                "pypdf 未安装，PDF 转录稿无法提取文本。请运行 "
                "`.venv/bin/pip install 'pypdf>=4.0'` 或重新 pip install -e ."
            )
            _pypdf_warned = True
        return ""

    try:
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning(f"PDF 提取文本失败 file={file_path}: {type(e).__name__}: {e}")
        return ""


def _read_body(file_path: Path | str) -> str:
    """Read a transcript file and return the prose body only."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".docx":
        return " ".join(line.strip() for line in _read_docx_text(path).splitlines() if line.strip())
    if suffix == ".pdf":
        return " ".join(line.strip() for line in _read_pdf_text(path).splitlines() if line.strip())

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
