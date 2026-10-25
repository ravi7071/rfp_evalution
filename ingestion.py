from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract raw text from a single PDF binary payload."""
    reader = PdfReader(BytesIO(pdf_bytes))
    pages_text = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(pages_text).strip()


def extract_text_from_pdf_path(pdf_path: str | Path) -> str:
    """Extract raw text from a local PDF file path."""
    with Path(pdf_path).open("rb") as file_obj:
        return extract_text_from_pdf_bytes(file_obj.read())


def extract_text_from_uploaded_file(uploaded_file: object) -> str:
    """Extract text from a Streamlit uploaded PDF object."""
    pdf_bytes = uploaded_file.getvalue()
    return extract_text_from_pdf_bytes(pdf_bytes)

