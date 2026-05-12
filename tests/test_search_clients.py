"""Tests for metadata parsing and deduplication."""

from app.models import Paper
from app.search_clients import abstract_from_openalex_index, deduplicate_papers, parse_arxiv_feed


def test_openalex_abstract_reconstruction() -> None:
    """Reconstructs OpenAlex inverted abstract text."""
    index = {"hello": [0], "world": [1], "again": [2]}

    assert abstract_from_openalex_index(index) == "hello world again"


def test_deduplicate_papers_merges_by_doi() -> None:
    """Merges duplicate records with stronger metadata."""
    papers = [
        Paper(title="First", doi="https://doi.org/10.1000/ABC", cited_by_count=1),
        Paper(title="First", doi="10.1000/abc", pdf_url="https://example.org/a.pdf", cited_by_count=5),
    ]

    deduped = deduplicate_papers(papers)

    assert len(deduped) == 1
    assert deduped[0].pdf_url == "https://example.org/a.pdf"
    assert deduped[0].cited_by_count == 5


def test_parse_arxiv_feed_extracts_pdf_url() -> None:
    """Parses basic arXiv Atom metadata."""
    feed = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/1234.5678v1</id>
        <title> Example Paper </title>
        <summary> This is a summary. </summary>
        <published>2024-01-01T00:00:00Z</published>
        <author><name>Ada Lovelace</name></author>
        <link title="pdf" href="http://arxiv.org/pdf/1234.5678v1" type="application/pdf"/>
      </entry>
    </feed>
    """

    papers = parse_arxiv_feed(feed)

    assert len(papers) == 1
    assert papers[0].title == "Example Paper"
    assert papers[0].pdf_url == "http://arxiv.org/pdf/1234.5678v1"

