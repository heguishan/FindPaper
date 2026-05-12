"""Open PDF download and validation utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx

from app.config import settings
from app.models import Paper
from app.utils import ensure_directory, paper_filename


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
        ensure_directory(destination_dir)
        if not paper.pdf_url:
            paper.download_status = "failed"
            paper.failure_reason = "无可用开放 PDF 链接"
            return False

        output_path = destination_dir / paper_filename(paper, suffix_hint=suffix_hint)
        try:
            response = await self.client.get(paper.pdf_url)
        except httpx.HTTPError as exc:
            paper.download_status = "failed"
            paper.failure_reason = f"下载请求失败：{exc.__class__.__name__}"
            return False

        if response.status_code >= 400:
            paper.download_status = "failed"
            paper.failure_reason = f"PDF 链接返回 HTTP {response.status_code}"
            return False

        content = response.content
        content_type = response.headers.get("content-type", "").lower()
        if not looks_like_pdf(content, content_type):
            paper.download_status = "failed"
            paper.failure_reason = "链接内容不是有效 PDF"
            return False
        if len(content) < settings.min_pdf_bytes:
            paper.download_status = "failed"
            paper.failure_reason = "PDF 文件过小，疑似错误页面"
            return False

        output_path.write_bytes(content)
        paper.file_path = output_path
        paper.download_status = "downloaded"
        paper.failure_reason = None
        return True


def looks_like_pdf(content: bytes, content_type: str = "") -> bool:
    """Checks whether response content appears to be a PDF."""
    stripped = content[:1024].lstrip()
    return stripped.startswith(b"%PDF") or ("application/pdf" in content_type and b"%PDF" in content[:4096])

