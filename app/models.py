"""Shared data models for paper discovery and job execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Paper:
    """Represents one academic paper candidate.

    Attributes:
        title: Paper title.
        doi: DOI without URL prefix when available.
        year: Publication year.
        authors: Ordered author display names.
        venue: Journal, conference, repository, or source name.
        landing_page_url: Human-readable page for the paper.
        pdf_url: Direct open PDF URL when available.
        source: Source that first produced the candidate.
        cited_by_count: Citation count from available metadata.
        normalized_citation_percentile: Optional field/year normalized percentile.
        is_open_access: Whether metadata marks the paper as open access.
        abstract: Abstract text when available.
        metadata: Extra source-specific fields.
        download_status: Download status such as pending, downloaded, or failed.
        failure_reason: Friendly reason when PDF download fails.
        file_path: Local PDF file path when downloaded.
        quality_score: Computed quality score.
        quality_reasons: Short explanation strings for the quality score.
    """

    title: str
    doi: Optional[str] = None
    year: Optional[int] = None
    authors: List[str] = field(default_factory=list)
    venue: Optional[str] = None
    landing_page_url: Optional[str] = None
    pdf_url: Optional[str] = None
    source: str = "unknown"
    cited_by_count: int = 0
    normalized_citation_percentile: Optional[float] = None
    is_open_access: bool = False
    abstract: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    download_status: str = "pending"
    failure_reason: Optional[str] = None
    file_path: Optional[Path] = None
    quality_score: float = 0.0
    quality_reasons: List[str] = field(default_factory=list)

    @property
    def unique_key(self) -> str:
        """Returns a stable key for deduplicating candidates."""
        if self.doi:
            return f"doi:{normalize_doi(self.doi)}"
        return f"title:{normalize_title(self.title)}"


@dataclass
class JobState:
    """Tracks one background search/download job."""

    job_id: str
    topic: str
    target_count: int
    output_dir: Path
    status: str = "queued"
    message: str = "Queued"
    downloaded_count: int = 0
    failed_count: int = 0
    high_quality_count: int = 0
    result: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)


def normalize_doi(doi: str) -> str:
    """Normalizes a DOI string for matching.

    Args:
        doi: DOI or DOI URL.

    Returns:
        Lower-cased DOI without URL decoration.
    """
    cleaned = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
    return cleaned.strip()


def normalize_title(title: str) -> str:
    """Normalizes a title for loose deduplication."""
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in title).split())

