"""DeepSeek-powered topic and keyword extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings


@dataclass
class TopicExtractionResult:
    """Structured result returned by an LLM topic extraction request.

    Attributes:
        abstract: Abstract identified by the model.
        keywords: Professional keywords in English when possible.
        search_topic: Search-ready English query.
        alternate_queries: Additional query variants for academic APIs.
        confidence: Confidence score between 0 and 1.
        notes: Short explanation of extraction choices.
    """

    abstract: str = ""
    keywords: List[str] = dataclass_field(default_factory=list)
    search_topic: str = ""
    alternate_queries: List[str] = dataclass_field(default_factory=list)
    confidence: float = 0.0
    notes: str = ""


@dataclass
class QueryOption:
    """One user-selectable academic search query option.

    Attributes:
        label: Short display label.
        query: Search-ready query string.
        reason: Why this option may work.
    """

    label: str
    query: str
    reason: str = ""


@dataclass
class SearchPlan:
    """DeepSeek-generated search plan for user confirmation.

    Attributes:
        field: English academic field constraint.
        core_terms: Core terms that should be treated as AND constraints.
        synonyms: Mapping from core term to synonyms or canonical alternatives.
        query_options: Candidate queries for the user to choose from.
        recommended_query: Default recommended query.
        confidence: Confidence score between 0 and 1.
        notes: Short explanation for the user.
        abstract: Abstract identified from uploaded PDF text when available.
    """

    field: str = ""
    core_terms: List[str] = dataclass_field(default_factory=list)
    synonyms: Dict[str, List[str]] = dataclass_field(default_factory=dict)
    query_options: List[QueryOption] = dataclass_field(default_factory=list)
    recommended_query: str = ""
    confidence: float = 0.0
    notes: str = ""
    abstract: str = ""


class DeepSeekClient:
    """Small DeepSeek Chat Completions client using httpx."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        """Initializes the client.

        Args:
            client: Optional injected HTTP client for tests.
        """
        self.client = client or httpx.AsyncClient(
            timeout=max(settings.request_timeout_seconds, 45),
            follow_redirects=True,
        )

    @property
    def enabled(self) -> bool:
        """Returns whether DeepSeek extraction is configured."""
        return bool(settings.enable_llm_topic_extraction and settings.deepseek_api_key)

    async def close(self) -> None:
        """Closes the underlying HTTP client."""
        await self.client.aclose()

    async def extract_topic_from_text(self, text: str, local_topic_hint: str = "") -> TopicExtractionResult:
        """Extracts abstract, expert keywords, and search queries from paper text.

        Args:
            text: Text extracted from the first pages of a PDF.
            local_topic_hint: Optional topic extracted by local rules.

        Returns:
            Structured topic extraction result.

        Raises:
            RuntimeError: If DeepSeek is not configured or the API response is invalid.
        """
        if not self.enabled:
            raise RuntimeError("DeepSeek API 未配置，请在 .env 中设置 DEEPSEEK_API_KEY。")

        truncated_text = text[:16000]
        system_prompt = (
            "You are an expert academic literature search assistant. "
            "Extract the paper abstract and professional search terms from noisy PDF text. "
            "Return only valid json using this shape: "
            '{"abstract": "...", "keywords": ["..."], "search_topic": "...", '
            '"alternate_queries": ["..."], "confidence": 0.0, "notes": "..."}'
        )
        user_prompt = (
            "Please read the following PDF text. It may contain broken line breaks, bilingual headings, "
            "or OCR/PDF extraction noise. Identify the Abstract/摘要 section if present. Then infer "
            "precise professional English keywords for academic database search. Prefer canonical "
            "terms over literal translation. The search_topic should be one concise English query "
            "with 4-10 terms. alternate_queries should contain 2-4 variants that improve open-access "
            "paper retrieval. Return json only.\n\n"
            f"Local topic hint: {local_topic_hint or 'N/A'}\n\nPDF text:\n{truncated_text}"
        )
        payload: Dict[str, Any] = {
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": 1800,
        }
        response = await self.client.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if not content:
            raise RuntimeError("DeepSeek 返回了空内容，请稍后重试。")
        return parse_topic_extraction_json(content)

    async def generate_search_plan(
        self,
        topic: str,
        field_hint: str = "",
        pdf_text: str = "",
        local_topic_hint: str = "",
    ) -> SearchPlan:
        """Generates a field-aware search plan for user confirmation.

        Args:
            topic: User-entered keywords or topic.
            field_hint: Optional user-entered field constraint.
            pdf_text: Optional text extracted from uploaded PDF.
            local_topic_hint: Optional local rule-based topic.

        Returns:
            Search plan with selectable query options.
        """
        if not self.enabled:
            raise RuntimeError("DeepSeek API 未配置，请在 .env 中设置 DEEPSEEK_API_KEY。")

        truncated_text = pdf_text[:14000]
        system_prompt = (
            "You are an expert academic search strategist. Convert Chinese or noisy academic input "
            "into precise English search plans. The goal is high-precision literature retrieval, not broad web search. "
            "Avoid medical/biological meanings unless the field explicitly asks for them. Return only valid JSON."
        )
        user_prompt = (
            "Build a search plan for open academic paper retrieval. Treat core_terms as AND constraints. "
            "Use synonyms only to create a few alternative query options, not broad OR expansion. "
            "If the input is Chinese, translate to canonical English academic terms. "
            "For example, 载流子俘获 in semiconductor defect physics should map toward carrier capture, "
            "carrier trapping, nonradiative recombination, defect physics, electron-phonon coupling when appropriate. "
            "Return JSON with this exact shape: "
            '{"field":"...", "core_terms":["..."], "synonyms":{"term":["..."]}, '
            '"query_options":[{"label":"...", "query":"...", "reason":"..."}], '
            '"recommended_query":"...", "confidence":0.0, "notes":"...", "abstract":"..."}.\n\n'
            f"User topic: {topic or 'N/A'}\n"
            f"User field hint: {field_hint or 'N/A'}\n"
            f"Local topic hint: {local_topic_hint or 'N/A'}\n"
            f"PDF text excerpt:\n{truncated_text or 'N/A'}"
        )
        payload: Dict[str, Any] = {
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 2200,
        }
        response = await self.client.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if not content:
            raise RuntimeError("DeepSeek 返回了空检索方案，请稍后重试。")
        return parse_search_plan_json(content, topic=topic, field_hint=field_hint)


def parse_topic_extraction_json(content: str) -> TopicExtractionResult:
    """Parses and validates DeepSeek's JSON topic extraction result."""
    data = json.loads(content)
    keywords = coerce_string_list(data.get("keywords"))[:12]
    alternate_queries = coerce_string_list(data.get("alternate_queries"))[:5]
    search_topic = str(data.get("search_topic") or "").strip()
    if not search_topic and keywords:
        search_topic = " ".join(keywords[:8])
    confidence = data.get("confidence", 0.0)
    try:
        confidence_value = max(0.0, min(float(confidence), 1.0))
    except (TypeError, ValueError):
        confidence_value = 0.0
    return TopicExtractionResult(
        abstract=str(data.get("abstract") or "").strip(),
        keywords=keywords,
        search_topic=search_topic,
        alternate_queries=alternate_queries,
        confidence=confidence_value,
        notes=str(data.get("notes") or "").strip(),
    )


def parse_search_plan_json(content: str, topic: str = "", field_hint: str = "") -> SearchPlan:
    """Parses and normalizes a DeepSeek search-plan JSON response."""
    data = json.loads(content)
    field_value = str(data.get("field") or field_hint or "").strip()
    core_terms = coerce_string_list(data.get("core_terms"))[:8]
    synonyms = coerce_synonyms(data.get("synonyms"))
    query_options = coerce_query_options(data.get("query_options"))[:5]
    recommended_query = str(data.get("recommended_query") or "").strip()
    if not recommended_query and query_options:
        recommended_query = query_options[0].query
    if not recommended_query:
        recommended_query = build_manual_recommended_query(topic, field_value, core_terms)
    if not query_options and recommended_query:
        query_options = [
            QueryOption(
                label="推荐查询",
                query=recommended_query,
                reason="根据用户输入和领域提示生成的默认 AND 风格查询。",
            )
        ]
    confidence = data.get("confidence", 0.0)
    try:
        confidence_value = max(0.0, min(float(confidence), 1.0))
    except (TypeError, ValueError):
        confidence_value = 0.0
    return SearchPlan(
        field=field_value,
        core_terms=core_terms,
        synonyms=synonyms,
        query_options=query_options,
        recommended_query=recommended_query,
        confidence=confidence_value,
        notes=str(data.get("notes") or "").strip(),
        abstract=str(data.get("abstract") or "").strip(),
    )


def fallback_search_plan(topic: str, field_hint: str = "", local_topic_hint: str = "") -> SearchPlan:
    """Builds a manual search plan when DeepSeek is unavailable."""
    base_topic = local_topic_hint or topic
    translated_topic = translate_known_chinese_terms(base_topic)
    translated_field = translate_known_chinese_terms(field_hint)
    terms = split_manual_terms(translated_topic)
    recommended_query = build_manual_recommended_query(base_topic, field_hint, terms)
    if translated_topic != base_topic or translated_field != field_hint:
        recommended_query = build_manual_recommended_query(translated_topic, translated_field, terms)
    return SearchPlan(
        field=(translated_field or field_hint).strip(),
        core_terms=terms[:8],
        synonyms={},
        query_options=[
            QueryOption(
                label="手动查询",
                query=recommended_query,
                reason="未配置 DeepSeek 时使用用户输入和领域提示组合检索。",
            )
        ],
        recommended_query=recommended_query,
        confidence=0.0,
        notes="未配置 DeepSeek API Key，已生成本地兜底检索方案。",
    )


def search_plan_to_dict(plan: SearchPlan) -> Dict[str, Any]:
    """Serializes a SearchPlan for API responses."""
    return {
        "field": plan.field,
        "core_terms": plan.core_terms,
        "synonyms": plan.synonyms,
        "query_options": [
            {"label": option.label, "query": option.query, "reason": option.reason}
            for option in plan.query_options
        ],
        "recommended_query": plan.recommended_query,
        "confidence": plan.confidence,
        "notes": plan.notes,
        "abstract": plan.abstract,
    }


def coerce_string_list(value: Any) -> List[str]:
    """Converts a JSON value into a clean list of strings."""
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.replace(";", ",").split(",")]
    elif isinstance(value, list):
        raw_items = [str(item).strip() for item in value]
    else:
        raw_items = []
    results: List[str] = []
    for item in raw_items:
        if item and item not in results:
            results.append(item)
    return results


def coerce_synonyms(value: Any) -> Dict[str, List[str]]:
    """Normalizes a synonyms JSON object."""
    if not isinstance(value, dict):
        return {}
    return {
        str(term).strip(): coerce_string_list(items)[:8]
        for term, items in value.items()
        if str(term).strip()
    }


def coerce_query_options(value: Any) -> List[QueryOption]:
    """Normalizes query option payloads."""
    if not isinstance(value, list):
        return []
    options: List[QueryOption] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            query = str(item.get("query") or "").strip()
            label = str(item.get("label") or f"查询 {index}").strip()
            reason = str(item.get("reason") or "").strip()
        else:
            query = str(item).strip()
            label = f"查询 {index}"
            reason = ""
        if query:
            options.append(QueryOption(label=label, query=query, reason=reason))
    return options


def build_manual_recommended_query(topic: str, field_hint: str = "", terms: Optional[List[str]] = None) -> str:
    """Builds a conservative AND-style query from manual input."""
    parts = []
    if field_hint.strip():
        parts.append(field_hint.strip())
    if terms:
        parts.extend(term for term in terms if term)
    elif topic.strip():
        parts.append(topic.strip())
    return " ".join(dict.fromkeys(parts)).strip()


def split_manual_terms(value: str) -> List[str]:
    """Splits manual input into conservative terms without losing phrases."""
    normalized = value.replace(";", ",").replace("，", ",").replace("；", ",")
    if "," in normalized:
        return coerce_string_list(normalized)
    return [normalized.strip()] if normalized.strip() else []


def translate_known_chinese_terms(value: str) -> str:
    """Translates a tiny local glossary for common user examples.

    This is only a fallback when DeepSeek is unavailable; configured DeepSeek
    remains the default source for professional translation and synonym mapping.
    """
    replacements = {
        "载流子俘获": "carrier capture carrier trapping",
        "半导体物理": "semiconductor physics",
        "半导体缺陷物理": "semiconductor defect physics",
        "缺陷物理": "defect physics",
        "光电材料": "optoelectronic materials",
        "宽禁带半导体": "wide bandgap semiconductors",
        "非辐射复合": "nonradiative recombination",
        "多声子": "multiphonon",
    }
    translated = value
    for chinese, english in replacements.items():
        translated = translated.replace(chinese, english)
    return translated
