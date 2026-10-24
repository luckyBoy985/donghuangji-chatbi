import io
import zipfile

import pytest

from backend.app.services.ingestion.parsers import validate_file_signature


def test_pdf_upload_requires_pdf_signature():
    with pytest.raises(ValueError, match="文件内容"):
        validate_file_signature("sales.pdf", b"not a pdf")

    validate_file_signature("sales.pdf", b"%PDF-1.7\ncontent")


def test_office_upload_requires_expected_zip_structure():
    with pytest.raises(ValueError, match="文件内容"):
        validate_file_signature("notes.docx", _zip({"other.txt": b"x"}))

    validate_file_signature(
        "notes.docx",
        _zip(
            {
                "[Content_Types].xml": b"<Types/>",
                "word/document.xml": b"<document/>",
            }
        ),
    )
    validate_file_signature(
        "data.xlsx",
        _zip(
            {
                "[Content_Types].xml": b"<Types/>",
                "xl/workbook.xml": b"<workbook/>",
            }
        ),
    )


def test_text_upload_rejects_binary_nul_bytes():
    with pytest.raises(ValueError, match="文件内容"):
        validate_file_signature("notes.md", b"text\x00binary")


def _zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()
