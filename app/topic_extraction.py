"""Extract search topics from uploaded academic PDFs."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


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

CHINESE_STOPWORDS = {
    "本文",
    "研究",
    "方法",
    "结果",
    "表明",
    "通过",
    "进行",
    "具有",
    "提出",
    "分析",
    "影响",
    "基于",
    "一种",
    "以及",
    "其中",
    "可以",
    "为了",
    "采用",
    "发现",
    "实现",
    "相关",
    "主要",
}

ABSTRACT_HEADING = r"(?:a\s*b\s*s\s*t\s*r\s*a\s*c\s*t|abstract|summary|摘要|摘\s*要)"
ABSTRACT_END_HEADING = (
    r"(?:keywords?|key\s*words?|index\s*terms?|"
    r"(?:1|i|Ⅰ|一)?\.?\s*(?:introduction|background|overview|引言|绪论|前言|背景)|"
    r"关键词|关键字)"
)


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
    normalized = normalize_extracted_text(text)
    patterns = [
        re.compile(
            rf"(?is)(?:^|\n|\r)\s*{ABSTRACT_HEADING}\s*[:：.\-—–]?\s*(.*?)"
            rf"(?=(?:\n|\r)\s*{ABSTRACT_END_HEADING}\b|$)"
        ),
        re.compile(
            rf"(?is)\b{ABSTRACT_HEADING}\b\s*[:：.\-—–]?\s*(.*?)"
            rf"(?=\s+{ABSTRACT_END_HEADING}\b|$)"
        ),
        re.compile(
            rf"(?s){ABSTRACT_HEADING}\s*[:：.\-—–]?\s*(.*?)"
            rf"(?={ABSTRACT_END_HEADING}|$)"
        ),
    ]

    for pattern in patterns:
        match = pattern.search(normalized)
        if match:
            abstract = clean_abstract(match.group(1))
            if is_usable_abstract(abstract):
                return abstract
    return None


def normalize_extracted_text(text: str) -> str:
    """Normalizes noisy text extracted from PDFs.

    Args:
        text: Raw text from pypdf or tests.

    Returns:
        Text with predictable spacing while preserving line breaks.
    """
    text = text.replace("\r", "\n")
    text = re.sub(r"-\s*\n\s*", "", text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_abstract(value: str) -> str:
    """Cleans extracted abstract text."""
    abstract = re.sub(r"\s+", " ", value).strip(" :：.-—–")
    abstract = re.sub(r"^(?:abstract|summary|摘要|摘\s*要)\s*[:：.\-—–]?\s*", "", abstract, flags=re.I)
    return abstract.strip()


def is_usable_abstract(abstract: str) -> bool:
    """Returns whether an extracted abstract has enough content."""
    if not abstract:
        return False
    english_words = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", abstract)
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", abstract)
    if len(english_words) >= 20:
        return True
    if len(chinese_chars) >= 40:
        return True
    return len(abstract) >= 160


def tokenize_keywords(text: str) -> Iterable[str]:
    """Tokenizes English academic text into keyword candidates."""
    for token in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text.lower()):
        token = token.strip("-")
        if len(token) >= 3 and token not in STOPWORDS:
            yield token


def tokenize_chinese_keywords(text: str) -> Iterable[str]:
    """Tokenizes Chinese abstract text into simple keyword candidates.

    This intentionally avoids external NLP dependencies. It creates short
    overlapping Chinese character chunks and ranks repeated chunks higher.
    """
    chinese_text = "".join(re.findall(r"[\u4e00-\u9fff]+", text))
    for size in (6, 5, 4, 3, 2):
        for index in range(0, max(len(chinese_text) - size + 1, 0)):
            token = chinese_text[index : index + size]
            if token not in CHINESE_STOPWORDS and not any(stop in token for stop in CHINESE_STOPWORDS):
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
    chinese_tokens = list(tokenize_chinese_keywords(abstract))
    counts = Counter(tokens)
    chinese_counts = Counter(chinese_tokens)
    phrase_counts: Counter[str] = Counter()
    for first, second in zip(tokens, tokens[1:]):
        if first != second:
            phrase_counts[f"{first} {second}"] += 1

    ranked_phrases = [
        phrase for phrase, count in phrase_counts.most_common() if count > 1 and len(phrase) <= 60
    ]
    ranked_terms = [term for term, _ in counts.most_common()]
    ranked_chinese_terms = [
        term for term, count in chinese_counts.most_common() if count > 1 or len(chinese_counts) <= max_keywords
    ]

    results: List[str] = []
    for candidate in [*ranked_phrases, *ranked_terms, *ranked_chinese_terms]:
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


def extract_local_topic_from_text(text: str) -> Tuple[Optional[str], Optional[str], List[str]]:
    """Extracts a topic from text using local Abstract heuristics.

    Args:
        text: Raw PDF text.

    Returns:
        Tuple of topic, abstract, and keyword list. Missing values are None or empty.
    """
    abstract = extract_abstract(text)
    if not abstract:
        return None, None, []
    keywords = extract_keywords_from_abstract(abstract)
    if not keywords:
        return None, abstract, []
    return " ".join(keywords), abstract, keywords
