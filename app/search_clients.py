"""Clients for open academic metadata and PDF sources."""

from __future__ import annotations

import html
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote_plus

import httpx

from app.config import settings
from app.models import Paper, normalize_doi


def abstract_from_openalex_index(index: Optional[Dict[str, List[int]]]) -> Optional[str]:
    """Reconstructs OpenAlex inverted-index abstracts.

    Args:
        index: OpenAlex abstract_inverted_index value.

    Returns:
        Plain abstract text, or None.
    """
    if not index:
        return None
    positions: Dict[int, str] = {}
    for word, indexes in index.items():
        for item in indexes:
            positions[item] = word
    return " ".join(positions[position] for position in sorted(positions))


def parse_openalex_work(item: Dict[str, Any]) -> Paper:
    """Parses one OpenAlex work object into a Paper."""
    best_oa = item.get("best_oa_location") or {}
    primary_location = item.get("primary_location") or {}
    source = (primary_location.get("source") or best_oa.get("source") or {}) if isinstance(
        primary_location, dict
    ) else {}
    authorships = item.get("authorships") or []
    authors = []
    for authorship in authorships[:8]:
        author = authorship.get("author") or {}
        if author.get("display_name"):
            authors.append(author["display_name"])

    percentile = None
    normalized = item.get("citation_normalized_percentile") or {}
    if normalized.get("value") is not None:
        percentile = float(normalized["value"])

    doi = item.get("doi")
    if doi:
        doi = normalize_doi(doi)

    pdf_url = best_oa.get("pdf_url") or (primary_location or {}).get("pdf_url")
    landing_page = item.get("doi") or best_oa.get("landing_page_url") or item.get("id")
    open_access = item.get("open_access") or {}

    return Paper(
        title=html.unescape(item.get("title") or item.get("display_name") or "Untitled"),
        doi=doi,
        year=item.get("publication_year"),
        authors=authors,
        venue=source.get("display_name") if isinstance(source, dict) else None,
        landing_page_url=landing_page,
        pdf_url=pdf_url,
        source="OpenAlex",
        cited_by_count=int(item.get("cited_by_count") or 0),
        normalized_citation_percentile=percentile,
        is_open_access=bool(open_access.get("is_oa") or pdf_url),
        abstract=abstract_from_openalex_index(item.get("abstract_inverted_index")),
        metadata={"openalex_id": item.get("id")},
    )


def parse_crossref_item(item: Dict[str, Any]) -> Paper:
    """Parses one Crossref work into a Paper."""
    title = " ".join(item.get("title") or []) or "Untitled"
    authors = []
    for author in item.get("author") or []:
        name = " ".join(filter(None, [author.get("given"), author.get("family")])).strip()
        if name:
            authors.append(name)

    year = None
    date_parts = (item.get("published-print") or item.get("published-online") or item.get("issued") or {}).get(
        "date-parts"
    )
    if date_parts and date_parts[0]:
        year = date_parts[0][0]

    doi = item.get("DOI")
    links = item.get("link") or []
    pdf_url = None
    for link in links:
        if "pdf" in (link.get("content-type") or "").lower():
            pdf_url = link.get("URL")
            break

    venue = " ".join(item.get("container-title") or []) or None
    return Paper(
        title=html.unescape(title),
        doi=normalize_doi(doi) if doi else None,
        year=year,
        authors=authors,
        venue=venue,
        landing_page_url=item.get("URL"),
        pdf_url=pdf_url,
        source="Crossref",
        cited_by_count=int(item.get("is-referenced-by-count") or 0),
        is_open_access=bool(pdf_url),
        abstract=strip_html(item.get("abstract")),
        metadata={"crossref_type": item.get("type")},
    )


def parse_semantic_scholar_item(item: Dict[str, Any]) -> Paper:
    """Parses one Semantic Scholar paper result into a Paper."""
    external_ids = item.get("externalIds") or {}
    doi = external_ids.get("DOI")
    open_pdf = item.get("openAccessPdf") or {}
    authors = [author.get("name") for author in item.get("authors") or [] if author.get("name")]
    return Paper(
        title=html.unescape(item.get("title") or "Untitled"),
        doi=normalize_doi(doi) if doi else None,
        year=item.get("year"),
        authors=authors,
        venue=item.get("venue"),
        landing_page_url=item.get("url"),
        pdf_url=open_pdf.get("url"),
        source="Semantic Scholar",
        cited_by_count=int(item.get("citationCount") or 0),
        is_open_access=bool(open_pdf.get("url") or item.get("isOpenAccess")),
        abstract=item.get("abstract"),
        metadata={"paper_id": item.get("paperId")},
    )


def strip_html(value: Optional[str]) -> Optional[str]:
    """Strips simple HTML tags from metadata fields."""
    if not value:
        return None
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


class AcademicSearchClient:
    """Aggregates open academic search APIs."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        """Initializes the client.

        Args:
            client: Optional injected HTTP client for tests.
        """
        self.client = client or httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True)

    async def close(self) -> None:
        """Closes the underlying HTTP client."""
        await self.client.aclose()

    async def search(self, topic: str, target_count: int) -> List[Paper]:
        """Searches all supported open metadata sources and deduplicates results.

        Args:
            topic: Query topic or keywords.
            target_count: Requested number of downloadable PDFs.

        Returns:
            Deduplicated candidate papers.
        """
        per_source = max(target_count * settings.max_candidates_multiplier, 20)
        candidates: List[Paper] = []
        for searcher in (
            self.search_openalex,
            self.search_semantic_scholar,
            self.search_crossref,
            self.search_arxiv,
        ):
            try:
                candidates.extend(await searcher(topic, per_source))
            except httpx.HTTPError:
                continue

        enriched = await self.enrich_with_unpaywall(candidates)
        return deduplicate_papers(enriched)

    async def search_openalex(self, topic: str, limit: int) -> List[Paper]:
        """Searches OpenAlex works."""
        params = {
            "search": topic,
            "per-page": min(limit, 200),
            "mailto": settings.contact_email,
            "sort": "cited_by_count:desc",
        }
        response = await self.client.get("https://api.openalex.org/works", params=params)
        response.raise_for_status()
        return [parse_openalex_work(item) for item in response.json().get("results", [])]

    async def search_crossref(self, topic: str, limit: int) -> List[Paper]:
        """Searches Crossref works."""
        headers = {"User-Agent": f"FindPaper/0.1 (mailto:{settings.contact_email})"}
        params = {
            "query.bibliographic": topic,
            "rows": min(limit, 100),
            "sort": "is-referenced-by-count",
            "order": "desc",
            "mailto": settings.contact_email,
        }
        response = await self.client.get("https://api.crossref.org/works", params=params, headers=headers)
        response.raise_for_status()
        items = response.json().get("message", {}).get("items", [])
        return [parse_crossref_item(item) for item in items]

    async def search_semantic_scholar(self, topic: str, limit: int) -> List[Paper]:
        """Searches Semantic Scholar Graph API."""
        headers = {}
        if settings.semantic_scholar_api_key:
            headers["x-api-key"] = settings.semantic_scholar_api_key
        params = {
            "query": topic,
            "limit": min(limit, 100),
            "fields": "title,year,authors,venue,url,abstract,citationCount,isOpenAccess,openAccessPdf,externalIds",
        }
        response = await self.client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params=params,
            headers=headers,
        )
        response.raise_for_status()
        return [parse_semantic_scholar_item(item) for item in response.json().get("data", [])]

    async def search_arxiv(self, topic: str, limit: int) -> List[Paper]:
        """Searches arXiv's Atom API."""
        url = (
            "https://export.arxiv.org/api/query?"
            f"search_query=all:{quote_plus(topic)}&start=0&max_results={min(limit, 100)}"
            "&sortBy=relevance&sortOrder=descending"
        )
        response = await self.client.get(url)
        response.raise_for_status()
        return parse_arxiv_feed(response.text)

    async def enrich_with_unpaywall(self, papers: Iterable[Paper]) -> List[Paper]:
        """Adds Unpaywall PDF links for DOI papers when possible."""
        enriched: List[Paper] = []
        seen_dois = set()
        for paper in papers:
            if not paper.pdf_url and paper.doi and paper.doi not in seen_dois:
                seen_dois.add(paper.doi)
                try:
                    unpaywall = await self.fetch_unpaywall(paper.doi)
                    if unpaywall:
                        paper.pdf_url = unpaywall.get("pdf_url") or paper.pdf_url
                        paper.landing_page_url = unpaywall.get("landing_page_url") or paper.landing_page_url
                        paper.is_open_access = bool(paper.pdf_url or unpaywall.get("is_oa"))
                except httpx.HTTPError:
                    pass
            enriched.append(paper)
        return enriched

    async def fetch_unpaywall(self, doi: str) -> Optional[Dict[str, Any]]:
        """Fetches open-access location metadata from Unpaywall."""
        response = await self.client.get(
            f"https://api.unpaywall.org/v2/{quote_plus(normalize_doi(doi))}",
            params={"email": settings.contact_email},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        best = data.get("best_oa_location") or {}
        return {
            "is_oa": data.get("is_oa"),
            "pdf_url": best.get("url_for_pdf"),
            "landing_page_url": best.get("url"),
        }


def deduplicate_papers(papers: Iterable[Paper]) -> List[Paper]:
    """Deduplicates papers and merges useful metadata.

    Args:
        papers: Candidate papers.

    Returns:
        Deduplicated list preserving first-seen priority.
    """
    merged: Dict[str, Paper] = {}
    for paper in papers:
        key = paper.unique_key
        if key not in merged:
            merged[key] = paper
            continue
        existing = merged[key]
        merge_paper_metadata(existing, paper)
    return list(merged.values())


def merge_paper_metadata(target: Paper, source: Paper) -> None:
    """Merges missing or stronger metadata from source into target."""
    target.doi = target.doi or source.doi
    target.year = target.year or source.year
    target.authors = target.authors or source.authors
    target.venue = target.venue or source.venue
    target.landing_page_url = target.landing_page_url or source.landing_page_url
    target.pdf_url = target.pdf_url or source.pdf_url
    target.abstract = target.abstract or source.abstract
    target.is_open_access = target.is_open_access or source.is_open_access
    target.cited_by_count = max(target.cited_by_count, source.cited_by_count)
    if target.normalized_citation_percentile is None:
        target.normalized_citation_percentile = source.normalized_citation_percentile
    target.metadata.update({key: value for key, value in source.metadata.items() if value})


def parse_arxiv_feed(feed_xml: str) -> List[Paper]:
    """Parses an arXiv Atom response using the standard library."""
    import xml.etree.ElementTree as ET

    namespace = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(feed_xml)
    papers: List[Paper] = []
    for entry in root.findall("atom:entry", namespace):
        title = re.sub(r"\s+", " ", entry.findtext("atom:title", default="", namespaces=namespace)).strip()
        summary = re.sub(r"\s+", " ", entry.findtext("atom:summary", default="", namespaces=namespace)).strip()
        published = entry.findtext("atom:published", default="", namespaces=namespace)
        year = int(published[:4]) if published[:4].isdigit() else None
        authors = [
            author.findtext("atom:name", default="", namespaces=namespace)
            for author in entry.findall("atom:author", namespace)
        ]
        pdf_url = None
        landing_url = entry.findtext("atom:id", default="", namespaces=namespace)
        doi = entry.findtext("arxiv:doi", default="", namespaces=namespace) or None
        for link in entry.findall("atom:link", namespace):
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href")
                break
        papers.append(
            Paper(
                title=html.unescape(title or "Untitled"),
                doi=normalize_doi(doi) if doi else None,
                year=year,
                authors=[author for author in authors if author],
                venue="arXiv",
                landing_page_url=landing_url,
                pdf_url=pdf_url,
                source="arXiv",
                is_open_access=bool(pdf_url),
                abstract=summary,
            )
        )
    return papers

