"""Tests for PDF validation."""

from app.downloader import candidate_urls_for_paper, discover_pdf_links, looks_like_pdf
from app.models import Paper


def test_looks_like_pdf_detects_pdf_header() -> None:
    """Accepts content starting with a PDF header."""
    assert looks_like_pdf(b"%PDF-1.7\ncontent", "")


def test_looks_like_pdf_rejects_html() -> None:
    """Rejects HTML error pages."""
    assert not looks_like_pdf(b"<html>not a pdf</html>", "text/html")


def test_candidate_urls_include_open_fallbacks() -> None:
    """Builds a richer download candidate list from common open metadata."""
    paper = Paper(
        title="Example",
        doi="10.1000/example",
        landing_page_url="https://arxiv.org/abs/2401.12345",
        metadata={"pdf_urls": ["https://example.org/open.pdf"]},
    )

    urls = candidate_urls_for_paper(paper)

    assert urls[:2] == ["https://example.org/open.pdf", "https://arxiv.org/pdf/2401.12345.pdf"]
    assert "https://doi.org/10.1000/example" in urls


def test_discover_pdf_links_from_html_landing_page() -> None:
    """Finds citation PDF metadata and relative PDF anchors."""
    html = b"""
    <html>
      <head><meta name="citation_pdf_url" content="/paper.pdf"></head>
      <body><a href="/download?type=pdf">PDF</a></body>
    </html>
    """

    urls = discover_pdf_links(html, "https://example.org/article/1")

    assert urls == ["https://example.org/paper.pdf", "https://example.org/download?type=pdf"]
