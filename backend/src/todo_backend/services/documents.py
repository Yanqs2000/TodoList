from pathlib import Path

from docx import Document
from pypdf import PdfReader

DOCUMENT_MAX_CHARS = 20_000
_TRUNCATION_MARKER = "\n...[TRUNCATED]"


class DocumentExtractionError(RuntimeError):
    pass


class DocumentEmptyError(DocumentExtractionError):
    pass


def extract_document_text(path: Path) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            text = _extract_pdf(path)
        elif suffix == ".docx":
            text = _extract_docx(path)
        else:  # .txt / .md
            text = path.read_text(encoding="utf-8")
    except DocumentExtractionError:
        raise
    except Exception as error:
        raise DocumentExtractionError("document could not be read") from error
    text = text.strip()
    if not text:
        raise DocumentEmptyError("document has no extractable text")
    if len(text) > DOCUMENT_MAX_CHARS:
        return text[:DOCUMENT_MAX_CHARS] + _TRUNCATION_MARKER
    return text


def _extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(path: Path) -> str:
    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)
