"""Tests for metadata parsing and deduplication."""

from app.models import Paper
from app.search_clients import (
    AcademicSearchClient,
    abstract_from_openalex_index,
    build_query_variants,
    deduplicate_papers,
    merge_paper_metadata,
    parse_arxiv_feed,
    parse_openalex_work,
    candidate_limit,
)


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
    assert "https://example.org/a.pdf" in deduped[0].pdf_urls


def test_merge_paper_metadata_preserves_pdf_fallbacks() -> None:
    """Keeps alternate PDF URLs from duplicate metadata sources."""
    target = Paper(title="First", doi="10.1000/abc", pdf_url="https://example.org/a.pdf")
    source = Paper(
        title="First",
        doi="10.1000/abc",
        pdf_url="https://example.org/b.pdf",
        metadata={"pdf_urls": ["https://example.org/c.pdf"]},
    )

    merge_paper_metadata(target, source)

    assert target.metadata["pdf_urls"] == [
        "https://example.org/a.pdf",
        "https://example.org/b.pdf",
        "https://example.org/c.pdf",
    ]


def test_parse_openalex_collects_all_open_pdf_locations() -> None:
    """Uses all OpenAlex OA locations, not just best_oa_location."""
    paper = parse_openalex_work(
        {
            "title": "Example",
            "doi": "https://doi.org/10.1000/abc",
            "best_oa_location": {"pdf_url": "https://example.org/best.pdf"},
            "primary_location": {"pdf_url": "https://example.org/primary.pdf"},
            "locations": [{"pdf_url": "https://example.org/other.pdf"}],
            "open_access": {"is_oa": True},
        }
    )

    assert paper.pdf_url == "https://example.org/best.pdf"
    assert paper.metadata["pdf_urls"] == [
        "https://example.org/best.pdf",
        "https://example.org/primary.pdf",
        "https://example.org/other.pdf",
    ]


async def test_fetch_unpaywall_collects_all_pdf_locations() -> None:
    """Collects every Unpaywall PDF location as downloader fallbacks."""

    def handler(request):
        import httpx

        return httpx.Response(
            200,
            json={
                "is_oa": True,
                "best_oa_location": {"url_for_pdf": "https://example.org/best.pdf"},
                "oa_locations": [
                    {"url_for_pdf": "https://example.org/best.pdf"},
                    {"url_for_pdf": "https://example.org/other.pdf"},
                ],
            },
        )

    import httpx

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    search = AcademicSearchClient(client=client)

    data = await search.fetch_unpaywall("10.1000/abc")

    assert data["pdf_urls"] == ["https://example.org/best.pdf", "https://example.org/other.pdf"]
    await client.aclose()


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


def test_build_query_variants_keeps_confirmed_query_first() -> None:
    """Keeps confirmed AND-style query first and avoids broad splitting."""
    variants = build_query_variants(
        "carrier capture nonradiative recombination electron phonon coupling defects",
        field_hint="semiconductor defect physics",
    )

    assert variants[0] == (
        "semiconductor defect physics carrier capture nonradiative recombination "
        "electron phonon coupling defects"
    )
    assert len(variants) <= 3


def test_candidate_limit_differs_by_search_mode() -> None:
    """Uses fewer candidates in fast mode than deep mode."""
    assert candidate_limit(10, "fast") < candidate_limit(10, "deep")
