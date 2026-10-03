"""Text extraction from dropped files. Stdlib only; pypdf is optional."""
from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path

TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".json", ".eml", ".log", ".yaml", ".yml"}
HTML_EXT = {".html", ".htm"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".svg", ".bmp", ".tif", ".tiff"}


def kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in TEXT_EXT:
        return "text"
    if ext in HTML_EXT:
        return "html"
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    if ext in IMAGE_EXT:
        return "image"
    return "binary"


def extract_text(path: Path) -> tuple[str, str | None]:
    """Return (text, warning). Never raises for unsupported formats."""
    k = kind(path)
    try:
        if k == "text":
            return path.read_text(encoding="utf-8", errors="replace"), None
        if k == "html":
            raw = path.read_text(encoding="utf-8", errors="replace")
            raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
            return html.unescape(re.sub(r"<[^>]+>", " ", raw)), None
        if k == "pdf":
            return _pdf(path)
        if k == "docx":
            return _docx(path), None
        if k == "image":
            return "", "image: linked only (no OCR)"
        return "", f"unsupported file type {path.suffix or '(none)'}: linked only"
    except Exception as e:  # corrupt files shouldn't stop a batch
        return "", f"text extraction failed: {e}"


def _pdf(path: Path) -> tuple[str, str | None]:
    try:
        from pypdf import PdfReader  # optional dependency
    except ImportError:
        return "", "pypdf not installed: PDF linked without text (pip install pypdf)"
    reader = PdfReader(str(path))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    return text, None if text.strip() else "PDF has no extractable text (scanned?)"


def _docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))
