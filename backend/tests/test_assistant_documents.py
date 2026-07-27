# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from pathlib import Path

import pytest
from docx import Document
from pypdf import PdfWriter

from todo_backend.services.documents import (
    DOCUMENT_MAX_CHARS,
    DocumentEmptyError,
    extract_document_text,
)

_MINIMAL_PDF = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 41>>stream
BT /F1 12 Tf 40 100 Td (Hello Plan) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000052 00000 n
0000000101 00000 n
0000000211 00000 n
0000000298 00000 n
trailer<</Root 1 0 R/Size 6>>
startxref
359
%%EOF
"""


def test_extracts_plain_text_and_markdown(tmp_path: Path) -> None:
    txt = tmp_path / "notes.txt"
    txt.write_text("周一例会 10:00", encoding="utf-8")
    md = tmp_path / "plan.md"
    md.write_text("# 计划\n- 买菜", encoding="utf-8")

    assert extract_document_text(txt) == "周一例会 10:00"
    assert "买菜" in extract_document_text(md)


def test_extracts_docx(tmp_path: Path) -> None:
    path = tmp_path / "schedule.docx"
    document = Document()
    document.add_paragraph("周三下午评审")
    document.save(path)  # type: ignore[reportArgumentType]

    assert "周三下午评审" in extract_document_text(path)


def test_extracts_pdf_text(tmp_path: Path) -> None:
    path = tmp_path / "hello.pdf"
    path.write_bytes(_MINIMAL_PDF)

    assert "Hello Plan" in extract_document_text(path)


def test_blank_pdf_raises_document_empty(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    with path.open("wb") as handle:
        writer.write(handle)

    with pytest.raises(DocumentEmptyError):
        extract_document_text(path)


def test_long_text_is_truncated(tmp_path: Path) -> None:
    path = tmp_path / "long.txt"
    path.write_text("x" * (DOCUMENT_MAX_CHARS + 100), encoding="utf-8")

    result = extract_document_text(path)

    assert len(result) == DOCUMENT_MAX_CHARS + len("\n...[TRUNCATED]")
    assert result.endswith("\n...[TRUNCATED]")
