"""Extract search topics from uploaded academic PDFs."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Iterable, List, Optional


STOPWORDS = {
    "about",
    "above",
    "across",
    "after",
    "again",
    "against",
    "also",
    "although",
    "among",
    "analysis",
    "and",
    "are",
    "because",
    "been",
    "between",
    "both",
    "can",
    "could",
    "data",
    "describe",
    "during",
    "each",
    "effect",
    "from",
    "has",
    "have",
    "however",
    "into",
    "may",
    "method",
    "model",
    "more",
    "most",
    "our",
    "paper",
    "present",
    "propose",
    "result",
    "results",
    "show",
    "shown",
    "significant",
    "study",
    "such",
    "than",
    "that",
    "the",
    "their",
    "these",
    "this",
    "through",
    "using",
    "was",
    "were",
    "which",
    "while",
    "with",
}


def extract_text_from_pdf(pdf_path: Path, max_pages: int = 5) -> str:
    """Extracts text from the first pages of a PDF.

    Args:
        pdf_path: Path to a PDF file.
        max_pages: Maximum number of pages to scan.

    Returns:
        Extracted text.

    Raises:
        ValueError: If the file is missing, unreadable, or has no text.
    """
    if not pdf_path.exists():
        raise ValueError(f"找不到上传的 PDF 文件：{pdf_path}")

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        page_text = []
        for page in reader.pages[:max_pages]:
            page_text.append(page.extract_text() or "")
    except ImportError as exc:
        raise ValueError("缺少 pypdf 依赖，请先安装 requirements.txt 后再上传 PDF。") from exc
    except Exception as exc:  # pragma: no cover - pypdf emits many concrete exceptions.
        raise ValueError(f"无法读取 PDF 文件，请确认文件未损坏：{exc}") from exc

    text = "\n".join(page_text).strip()
    if not text:
        raise ValueError("PDF 中未提取到可用文本，可能是扫描版图片 PDF。")
    return text


def extract_abstract(text: str) -> Optional[str]:
    """Extracts the Abstract section from academic text.

    Args:
        text: Raw extracted text.

    Returns:
        Abstract content, or None when no section can be identified.
    """
    normalized = re.sub(r"[ \t]+", " ", text)
    normalized = re.sub(r"\n+", "\n", normalized)
    pattern = re.compile(
        r"(?is)(?:^|\n)\s*(?:abstract|summary)\s*[:.\-]?\s*(.*?)"
        r"(?=\n\s*(?:1\.?\s*)?(?:introduction|keywords?|index terms|background)\b|$)"
    )
    match = pattern.search(normalized)
    if not match:
        return None
    abstract = re.sub(r"\s+", " ", match.group(1)).strip()
    if len(abstract.split()) < 20:
        return None
    return abstract


def tokenize_keywords(text: str) -> Iterable[str]:
    """Tokenizes English academic text into keyword candidates."""
    for token in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text.lower()):
        token = token.strip("-")
        if len(token) >= 3 and token not in STOPWORDS:
            yield token


def extract_keywords_from_abstract(abstract: str, max_keywords: int = 8) -> List[str]:
    """Extracts keywords from an abstract using local frequency heuristics.

    Args:
        abstract: Abstract text.
        max_keywords: Maximum keywords to return.

    Returns:
        Ordered keywords and short keyphrases.
    """
    tokens = list(tokenize_keywords(abstract))
    counts = Counter(tokens)
    phrase_counts: Counter[str] = Counter()
    for first, second in zip(tokens, tokens[1:]):
        if first != second:
            phrase_counts[f"{first} {second}"] += 1

    ranked_phrases = [
        phrase for phrase, count in phrase_counts.most_common() if count > 1 and len(phrase) <= 60
    ]
    ranked_terms = [term for term, _ in counts.most_common()]

    results: List[str] = []
    for candidate in [*ranked_phrases, *ranked_terms]:
        if candidate not in results:
            results.append(candidate)
        if len(results) >= max_keywords:
            break
    return results


def extract_topic_from_pdf(pdf_path: Path) -> str:
    """Extracts a search topic from a PDF's Abstract section.

    Args:
        pdf_path: Uploaded PDF path.

    Returns:
        A space-separated keyword topic.

    Raises:
        ValueError: If no Abstract section or keywords can be extracted.
    """
    text = extract_text_from_pdf(pdf_path)
    abstract = extract_abstract(text)
    if not abstract:
        raise ValueError("未识别到 Abstract 段落，请手动输入主题或关键词后继续。")
    keywords = extract_keywords_from_abstract(abstract)
    if not keywords:
        raise ValueError("已识别 Abstract，但未能提取有效关键词，请手动输入主题。")
    return " ".join(keywords)
