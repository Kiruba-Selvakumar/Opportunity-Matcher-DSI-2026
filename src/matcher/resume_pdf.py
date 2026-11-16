"""Read the text out of an uploaded resume PDF. Only PDFs are accepted."""
from __future__ import annotations

import io

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10


class ResumeError(ValueError):
    """The upload cannot be used. The message is safe to show to staff."""


def pdf_to_text(data: bytes) -> tuple[str, int]:
    """Return (text, page_count). Raises ResumeError with a plain message when the file cannot be read."""
    if not data:
        raise ResumeError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise ResumeError("The file is larger than 5 MB.")
    if not data.lstrip()[:5] == b"%PDF-":
        raise ResumeError("This is not a PDF file.")
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ResumeError("This PDF is password protected.")
        pages = reader.pages[:MAX_PAGES]
        text = "\n".join((p.extract_text() or "") for p in pages)
        n = len(reader.pages)
    except ResumeError:
        raise
    except (PyPdfError, ValueError, KeyError, OSError) as e:
        raise ResumeError("This PDF could not be read. It may be damaged.") from e
    if len(text.strip()) < 20:
        raise ResumeError("This PDF has no readable text. It may be a scan or a photo. Export it again as text.")
    return text, n
