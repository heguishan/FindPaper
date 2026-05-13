"""Open PDF download and validation utilities."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings
from app.models import Paper
from app.utils import ensure_directory, paper_filename


MAX_DOWNLOAD_ATTEMPTS = 10


class PaperDownloader:
    """Downloads and validates open-access PDF files."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        """Initializes the downloader.

        Args:
            client: Optional injected HTTP client.
        """
        self.client = client or httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": f"FindPaper/0.1 (mailto:{settings.contact_email})"},
        )

    async def close(self) -> None:
        """Closes the underlying HTTP client."""
        await self.client.aclose()

    async def download(self, paper: Paper, destination_dir: Path, suffix_hint: str = "") -> bool:
        """Downloads a paper PDF if a valid open PDF URL is available.

        Args:
            paper: Paper metadata to download.
            destination_dir: Directory where PDF should be saved.
            suffix_hint: Optional unique hint for file naming.

        Returns:
            True when the PDF was downloaded and validated.
        """
        output_path = destination_dir / paper_filename(paper, suffix_hint=suffix_hint)
        ensure_directory(destination_dir)
        attempted: List[str] = []
        small_pdf_seen = False
        candidates = candidate_urls_for_paper(paper)
        if not candidates:
            paper.download_status = "failed"
            paper.failure_reason = "无可用开放 PDF 链接"
            return False

        while candidates and len(attempted) < MAX_DOWNLOAD_ATTEMPTS:
            url = candidates.pop(0)
            if url in attempted:
                continue
            attempted.append(url)
            try:
                response = await self.client.get(url)
            except httpx.HTTPError:
                continue

            final_url = str(response.url)
            if final_url not in attempted:
                attempted.append(final_url)
            if response.status_code >= 400:
                continue

            content = response.content
            content_type = response.headers.get("content-type", "").lower()
            if looks_like_pdf(content, content_type):
                if len(content) < settings.min_pdf_bytes:
                    small_pdf_seen = True
                    continue
                output_path.write_bytes(content)
                paper.pdf_url = final_url
                paper.file_path = output_path
                paper.download_status = "downloaded"
                paper.failure_reason = None
                return True

            if looks_like_html(content, content_type):
                discovered = discover_pdf_links(content, final_url)
                candidates.extend(url for url in discovered if url not in attempted and url not in candidates)

        paper.download_status = "failed"
        if small_pdf_seen:
            paper.failure_reason = f"已尝试 {len(attempted)} 个开放链接，仅找到过小的疑似错误 PDF"
        elif attempted:
            paper.failure_reason = f"已尝试 {len(attempted)} 个开放链接，未找到有效 PDF"
        else:
            paper.failure_reason = "无可用开放 PDF 链接"
        return False


def looks_like_pdf(content: bytes, content_type: str = "") -> bool:
    """Checks whether response content appears to be a PDF."""
    stripped = content[:1024].lstrip()
    return stripped.startswith(b"%PDF") or ("application/pdf" in content_type and b"%PDF" in content[:4096])


def looks_like_html(content: bytes, content_type: str = "") -> bool:
    """Checks whether response content appears to be an HTML landing page."""
    stripped = content[:1024].lstrip().lower()
    return "text/html" in content_type or stripped.startswith((b"<!doctype html", b"<html"))


def candidate_urls_for_paper(paper: Paper) -> List[str]:
    """Builds an ordered list of open URLs that may lead to a PDF."""
    urls: List[str] = []
    add_unique(urls, normalize_candidate_url(paper.pdf_url))
    for url in paper.metadata.get("pdf_urls") or []:
        add_unique(urls, normalize_candidate_url(url))
    add_unique(urls, arxiv_pdf_url(paper.pdf_url))
    add_unique(urls, arxiv_pdf_url(paper.landing_page_url))
    add_unique(urls, pmc_pdf_url(paper.landing_page_url))
    add_unique(urls, normalize_candidate_url(paper.landing_page_url))
    if paper.doi:
        add_unique(urls, f"https://doi.org/{paper.doi}")
    return urls


def discover_pdf_links(content: bytes, base_url: str) -> List[str]:
    """Extracts likely public PDF links from an HTML landing page."""
    text = content.decode("utf-8", errors="ignore")
    candidates: List[str] = []
    patterns = [
        r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url["\']',
        r'<link[^>]+type=["\']application/pdf["\'][^>]+href=["\']([^"\']+)["\']',
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            url = html.unescape(match.group(1).strip())
            if is_likely_pdf_url(url) or "citation_pdf_url" in match.group(0).lower():
                add_unique(candidates, normalize_candidate_url(urljoin(base_url, url)))

    add_unique(candidates, arxiv_pdf_url(base_url))
    add_unique(candidates, pmc_pdf_url(base_url))
    return candidates


def normalize_candidate_url(url: Optional[str]) -> Optional[str]:
    """Normalizes common open repository URLs without changing publisher semantics."""
    if not url:
        return None
    cleaned = html.unescape(str(url).strip())
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc.endswith("arxiv.org"):
        return arxiv_pdf_url(cleaned) or cleaned.replace("http://", "https://", 1)
    return cleaned


def arxiv_pdf_url(url: Optional[str]) -> Optional[str]:
    """Returns a canonical arXiv PDF URL from an arXiv landing or PDF URL."""
    if not url:
        return None
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#]+)", url, flags=re.IGNORECASE)
    if not match:
        return None
    arxiv_id = match.group(1).removesuffix(".pdf")
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def pmc_pdf_url(url: Optional[str]) -> Optional[str]:
    """Returns the NCBI PMC PDF endpoint for public PMC article pages."""
    if not url:
        return None
    match = re.search(r"ncbi\.nlm\.nih\.gov/pmc/articles/(PMC\d+)", url, flags=re.IGNORECASE)
    if not match:
        return None
    return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{match.group(1)}/pdf/"


def is_likely_pdf_url(url: str) -> bool:
    """Checks whether a URL path or query looks like a PDF endpoint."""
    lowered = url.lower()
    return (
        ".pdf" in lowered
        or "/pdf/" in lowered
        or lowered.endswith("/pdf")
        or "download=pdf" in lowered
        or "type=pdf" in lowered
    )


def add_unique(values: List[str], value: Optional[str]) -> None:
    """Appends a non-empty URL only once."""
    if value and value not in values:
        values.append(value)
