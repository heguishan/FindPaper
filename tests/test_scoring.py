"""Tests for quality scoring and high-quality selection."""

from app.models import Paper
from app.scoring import score_paper, select_high_quality_papers


def test_score_paper_uses_metadata_signals() -> None:
    """Scores papers with DOI, venue, citations, and OA metadata higher."""
    paper = Paper(
        title="Important Paper",
        doi="10.1000/test",
        year=2025,
        venue="Nature",
        cited_by_count=100,
        pdf_url="https://example.org/paper.pdf",
        is_open_access=True,
        abstract="Abstract text.",
    )

    score = score_paper(paper)

    assert score > 40
    assert paper.quality_reasons


def test_select_high_quality_papers_requires_downloaded_files() -> None:
    """Only downloaded papers are eligible for high-quality copying."""
    papers = [
        Paper(title="Downloaded", cited_by_count=20, download_status="downloaded"),
        Paper(title="Failed", cited_by_count=999, download_status="failed"),
    ]

    selected = select_high_quality_papers(papers)

    assert [paper.title for paper in selected] == ["Downloaded"]

