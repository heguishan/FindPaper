"""Tests for filesystem helper utilities."""

from app.models import Paper
from app.utils import paper_filename, sanitize_name


def test_sanitize_name_removes_invalid_characters() -> None:
    """Removes path separators and Windows-invalid characters."""
    assert sanitize_name('a/b:c*?"paper"') == "a b c paper"


def test_paper_filename_is_pdf_and_stable() -> None:
    """Builds a safe PDF file name from paper metadata."""
    paper = Paper(title="A Study / About: Testing?", doi="10.1000/example", year=2024, authors=["Ada Lovelace"])

    filename = paper_filename(paper)

    assert filename.endswith(".pdf")
    assert "/" not in filename
    assert ":" not in filename

