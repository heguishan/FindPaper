"""Utility helpers for safe paths and file names."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

from app.models import Paper


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_name(value: str, fallback: str = "untitled", max_length: int = 120) -> str:
    """Sanitizes user-controlled names for filesystem use.

    Args:
        value: Raw name from user input or metadata.
        fallback: Name to use if the cleaned value is empty.
        max_length: Maximum character length for the returned name.

    Returns:
        A filesystem-safe name.
    """
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        cleaned = fallback
    if cleaned.upper() in WINDOWS_RESERVED_NAMES:
        cleaned = f"{cleaned}_item"
    return cleaned[:max_length].strip(" .") or fallback


def ensure_directory(path: Path) -> Path:
    """Creates a directory if needed and returns it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def paper_filename(paper: Paper, suffix_hint: Optional[str] = None) -> str:
    """Builds a stable PDF file name for a paper.

    Args:
        paper: Paper metadata.
        suffix_hint: Optional unique hint when DOI is missing.

    Returns:
        A sanitized PDF file name.
    """
    year = str(paper.year or "unknown")
    first_author = paper.authors[0] if paper.authors else "unknown-author"
    identity = paper.doi or paper.title or suffix_hint or "paper"
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10]
    base = f"{year}_{first_author}_{paper.title[:80]}_{digest}"
    return f"{sanitize_name(base, fallback='paper', max_length=150)}.pdf"

