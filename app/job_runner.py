"""Background orchestration for paper search jobs."""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.downloader import PaperDownloader
from app.models import JobState, Paper
from app.reports import write_all_papers_csv, write_high_quality_report, write_unavailable_reports
from app.scoring import score_paper, select_high_quality_papers
from app.search_clients import AcademicSearchClient
from app.utils import ensure_directory, sanitize_name


class JobManager:
    """Manages in-memory background jobs for the local web application."""

    def __init__(self) -> None:
        """Initializes an empty job registry."""
        self.jobs: Dict[str, JobState] = {}

    def create_job(
        self,
        topic: str,
        target_count: int,
        output_dir: Path,
        field_hint: str = "",
        search_mode: str = "fast",
    ) -> JobState:
        """Creates and schedules a background job."""
        job_id = uuid.uuid4().hex
        job = JobState(
            job_id=job_id,
            topic=topic,
            target_count=target_count,
            output_dir=output_dir,
        )
        job.result = {"field_hint": field_hint, "search_mode": search_mode}
        self.jobs[job_id] = job
        self.add_event(job, "queued", "任务已创建")
        asyncio.create_task(self.run_job(job))
        return job

    def get_job(self, job_id: str) -> Optional[JobState]:
        """Returns a job by ID."""
        return self.jobs.get(job_id)

    def add_event(self, job: JobState, status: str, message: str, **payload: Any) -> None:
        """Adds a status event to a job."""
        job.status = status
        job.message = message
        event = {"status": status, "message": message, **payload}
        job.events.append(event)

    async def run_job(self, job: JobState) -> None:
        """Runs a paper search/download/report job."""
        search_client = AcademicSearchClient()
        downloader = PaperDownloader()
        try:
            topic_name = sanitize_name(job.topic, fallback="topic")
            paper_dir = ensure_directory(job.output_dir / topic_name)
            high_quality_dir = ensure_directory(job.output_dir / f"{topic_name}高质量")
            reports_dir = ensure_directory(paper_dir / "reports")

            field_hint = str(job.result.get("field_hint") or "")
            search_mode = str(job.result.get("search_mode") or "fast")
            self.add_event(job, "running", f"正在检索候选文献（{search_mode} 模式）")
            papers = await search_client.search(
                job.topic,
                job.target_count,
                field_hint=field_hint,
                search_mode=search_mode,
            )
            if not papers:
                self.add_event(job, "completed", "未找到候选文献")
                job.result = {
                    "paper_dir": str(paper_dir),
                    "high_quality_dir": str(high_quality_dir),
                    "reports_dir": str(reports_dir),
                    "downloaded_count": 0,
                    "failed_count": 0,
                    "high_quality_count": 0,
                }
                return

            self.add_event(job, "running", f"找到 {len(papers)} 篇候选文献，开始下载开放 PDF")
            await self.download_until_target(job, papers, downloader, paper_dir)

            for paper in papers:
                score_paper(paper)

            high_quality = select_high_quality_papers(papers)
            for paper in high_quality:
                if paper.file_path:
                    target = high_quality_dir / paper.file_path.name
                    shutil.copy2(paper.file_path, target)

            reports = [
                write_all_papers_csv(papers, reports_dir),
                *write_unavailable_reports(papers, reports_dir),
                write_high_quality_report(high_quality, reports_dir),
            ]

            job.downloaded_count = len([paper for paper in papers if paper.download_status == "downloaded"])
            job.failed_count = len([paper for paper in papers if paper.download_status == "failed"])
            job.high_quality_count = len(high_quality)
            shortfall = max(job.target_count - job.downloaded_count, 0)
            message = f"任务完成，成功下载 {job.downloaded_count} 篇"
            if shortfall:
                message += f"，开放 PDF 不足目标数量，差额 {shortfall} 篇"

            job.result.update({
                "topic": job.topic,
                "field_hint": field_hint,
                "search_mode": search_mode,
                "paper_dir": str(paper_dir),
                "high_quality_dir": str(high_quality_dir),
                "reports_dir": str(reports_dir),
                "reports": [str(path) for path in reports],
                "downloaded_count": job.downloaded_count,
                "failed_count": job.failed_count,
                "high_quality_count": job.high_quality_count,
                "shortfall": shortfall,
            })
            self.add_event(job, "completed", message, result=job.result)
        except Exception as exc:  # Keeps UI friendly instead of losing background errors.
            self.add_event(job, "failed", f"任务失败：{exc}")
        finally:
            await search_client.close()
            await downloader.close()

    async def download_until_target(
        self,
        job: JobState,
        papers: List[Paper],
        downloader: PaperDownloader,
        paper_dir: Path,
    ) -> None:
        """Downloads candidate PDFs until the target count or candidates are exhausted."""
        downloaded = 0
        for index, paper in enumerate(papers, start=1):
            if downloaded >= job.target_count:
                paper.download_status = "skipped"
                paper.failure_reason = "已达到目标下载数量"
                continue

            self.add_event(job, "running", f"正在下载 {index}/{len(papers)}：{paper.title[:80]}")
            success = await downloader.download(paper, paper_dir, suffix_hint=str(index))
            if success:
                downloaded += 1
                job.downloaded_count = downloaded
            else:
                job.failed_count += 1


job_manager = JobManager()


def resolve_output_dir(raw_output_dir: str) -> Path:
    """Resolves and validates the user-selected output directory.

    Args:
        raw_output_dir: User-provided path string.

    Returns:
        Absolute Path for output.

    Raises:
        ValueError: If path is invalid or points to an existing file.
    """
    output_dir = Path(raw_output_dir).expanduser() if raw_output_dir else settings.default_output_dir
    output_dir = output_dir.resolve()
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError("输出目录指向了一个文件，请选择文件夹路径。")
    ensure_directory(output_dir)
    return output_dir
