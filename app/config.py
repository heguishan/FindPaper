"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    contact_email: str = os.getenv("CONTACT_EMAIL", "findpaper@example.com")
    semantic_scholar_api_key: str = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    enable_llm_topic_extraction: bool = os.getenv("ENABLE_LLM_TOPIC_EXTRACTION", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "25"))
    max_candidates_multiplier: int = int(os.getenv("MAX_CANDIDATES_MULTIPLIER", "5"))
    min_pdf_bytes: int = int(os.getenv("MIN_PDF_BYTES", "1024"))
    default_output_dir: Path = Path(os.getenv("DEFAULT_OUTPUT_DIR", "downloads")).resolve()


settings = Settings()
