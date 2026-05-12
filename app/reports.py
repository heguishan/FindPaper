"""Report generation for paper download jobs."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, List

from app.models import Paper
from app.utils import ensure_directory


CSV_FIELDS = [
    "title",
    "doi",
    "year",
    "venue",
    "source",
    "cited_by_count",
    "quality_score",
    "download_status",
    "failure_reason",
    "pdf_url",
    "landing_page_url",
    "file_path",
]


def write_all_papers_csv(papers: Iterable[Paper], reports_dir: Path) -> Path:
    """Writes all candidate metadata to CSV."""
    ensure_directory(reports_dir)
    path = reports_dir / "all_papers.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for paper in papers:
            writer.writerow(_paper_row(paper))
    return path


def write_unavailable_reports(papers: Iterable[Paper], reports_dir: Path) -> List[Path]:
    """Writes unavailable paper reports in CSV and Markdown formats."""
    ensure_directory(reports_dir)
    unavailable = [paper for paper in papers if paper.download_status == "failed"]
    csv_path = reports_dir / "unavailable_papers.csv"
    md_path = reports_dir / "unavailable_papers.md"

    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for paper in unavailable:
            writer.writerow(_paper_row(paper))

    with md_path.open("w", encoding="utf-8") as file:
        file.write("# 无法下载的文献\n\n")
        if not unavailable:
            file.write("所有选中文献均已成功下载。\n")
        for index, paper in enumerate(unavailable, start=1):
            file.write(f"## {index}. {paper.title}\n\n")
            file.write(f"- DOI: {paper.doi or 'N/A'}\n")
            file.write(f"- 年份: {paper.year or 'N/A'}\n")
            file.write(f"- 来源: {paper.source}\n")
            file.write(f"- 期刊/会议: {paper.venue or 'N/A'}\n")
            file.write(f"- 失败原因: {paper.failure_reason or '无可用开放 PDF'}\n")
            file.write(f"- 落地页: {paper.landing_page_url or 'N/A'}\n\n")
    return [csv_path, md_path]


def write_high_quality_report(papers: Iterable[Paper], reports_dir: Path) -> Path:
    """Writes a Markdown report explaining high-quality selections."""
    ensure_directory(reports_dir)
    high_quality = sorted(papers, key=lambda item: item.quality_score, reverse=True)
    path = reports_dir / "high_quality_papers.md"
    with path.open("w", encoding="utf-8") as file:
        file.write("# 高质量文献\n\n")
        if not high_quality:
            file.write("未筛选出高质量文献。\n")
        for index, paper in enumerate(high_quality, start=1):
            file.write(f"## {index}. {paper.title}\n\n")
            file.write(f"- DOI: {paper.doi or 'N/A'}\n")
            file.write(f"- 年份: {paper.year or 'N/A'}\n")
            file.write(f"- 质量评分: {paper.quality_score}\n")
            file.write(f"- 入选原因: {'; '.join(paper.quality_reasons)}\n")
            file.write(f"- 文件: {paper.file_path or 'N/A'}\n\n")
    return path


def _paper_row(paper: Paper) -> dict:
    """Converts a Paper to a report row."""
    return {
        "title": paper.title,
        "doi": paper.doi or "",
        "year": paper.year or "",
        "venue": paper.venue or "",
        "source": paper.source,
        "cited_by_count": paper.cited_by_count,
        "quality_score": paper.quality_score,
        "download_status": paper.download_status,
        "failure_reason": paper.failure_reason or "",
        "pdf_url": paper.pdf_url or "",
        "landing_page_url": paper.landing_page_url or "",
        "file_path": str(paper.file_path or ""),
    }
