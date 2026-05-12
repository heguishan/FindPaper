"""Quality scoring for downloaded papers."""

from __future__ import annotations

import math
from datetime import date
from typing import Iterable, List

from app.models import Paper


def score_paper(paper: Paper) -> float:
    """Scores one paper and stores human-readable reasons.

    Args:
        paper: Paper to score.

    Returns:
        Numeric quality score.
    """
    reasons: List[str] = []
    score = 0.0

    if paper.normalized_citation_percentile is not None:
        percentile = max(0.0, min(float(paper.normalized_citation_percentile), 1.0))
        score += percentile * 45
        reasons.append(f"field/year citation percentile {percentile:.2f}")
    elif paper.cited_by_count:
        citation_score = min(math.log1p(paper.cited_by_count) / math.log(501), 1.0) * 35
        score += citation_score
        reasons.append(f"{paper.cited_by_count} citations")

    current_year = date.today().year
    if paper.year:
        age = max(current_year - paper.year, 0)
        if age <= 5:
            score += 15
            reasons.append("recent publication")
        elif age <= 10:
            score += 8
            reasons.append("reasonably recent publication")

    if paper.venue:
        score += 15
        reasons.append(f"venue available: {paper.venue}")
    if paper.doi:
        score += 10
        reasons.append("DOI available")
    if paper.is_open_access or paper.pdf_url:
        score += 10
        reasons.append("open-access PDF available")
    if paper.abstract:
        score += 5
        reasons.append("abstract metadata available")

    paper.quality_score = round(score, 2)
    paper.quality_reasons = reasons or ["limited metadata available"]
    return paper.quality_score


def select_high_quality_papers(papers: Iterable[Paper]) -> List[Paper]:
    """Selects the default high-quality subset from downloaded papers.

    Args:
        papers: Papers to consider. Only downloaded papers are selected.

    Returns:
        Ranked high-quality papers.
    """
    downloaded = [paper for paper in papers if paper.download_status == "downloaded"]
    for paper in downloaded:
        score_paper(paper)

    ranked = sorted(downloaded, key=lambda item: item.quality_score, reverse=True)
    if not ranked:
        return []
    if len(ranked) < 3:
        return ranked[:1]

    count = max(3, math.ceil(len(ranked) * 0.30))
    return ranked[:count]

