import pytest

from matcher.resume_pdf import ResumeError, pdf_to_text

from .test_api import make_pdf


def test_reads_text_and_pages():
    text, pages = pdf_to_text(make_pdf(["Skills: Python, SQL and Git", "CGPA: 8.1 out of ten"]))
    assert "Python" in text and "CGPA" in text and pages == 1


@pytest.mark.parametrize("data,msg", [
    (b"", "empty"),
    (b"just some text, not a pdf at all", "not a PDF"),
    (b"%PDF-1.4 garbage that is not a real pdf", "could not be read"),
    (b"%PDF-" + b"x" * (5 * 1024 * 1024 + 10), "larger than 5 MB"),
])
def test_bad_files_get_plain_messages(data, msg):
    with pytest.raises(ResumeError, match=msg):
        pdf_to_text(data)


def test_pdf_without_text_is_rejected():
    with pytest.raises(ResumeError, match="no readable text"):
        pdf_to_text(make_pdf([]))
