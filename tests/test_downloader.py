"""Tests for PDF validation."""

from app.downloader import looks_like_pdf


def test_looks_like_pdf_detects_pdf_header() -> None:
    """Accepts content starting with a PDF header."""
    assert looks_like_pdf(b"%PDF-1.7\ncontent", "")


def test_looks_like_pdf_rejects_html() -> None:
    """Rejects HTML error pages."""
    assert not looks_like_pdf(b"<html>not a pdf</html>", "text/html")

