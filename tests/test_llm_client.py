"""Tests for DeepSeek response parsing."""

from app.llm_client import fallback_search_plan, parse_search_plan_json, parse_topic_extraction_json


def test_parse_topic_extraction_json_builds_search_topic() -> None:
    """Parses a valid JSON response from DeepSeek."""
    result = parse_topic_extraction_json(
        """
        {
          "abstract": "This paper studies carrier trapping.",
          "keywords": ["nonradiative carrier capture", "multiphonon emission"],
          "search_topic": "nonradiative carrier capture multiphonon emission defects",
          "alternate_queries": ["carrier trapping electron phonon coupling"],
          "confidence": 0.88,
          "notes": "ok"
        }
        """
    )

    assert result.confidence == 0.88
    assert result.keywords[0] == "nonradiative carrier capture"
    assert "multiphonon" in result.search_topic


def test_parse_search_plan_json_supports_field_and_query_options() -> None:
    """Parses DeepSeek search plan output for the two-step workflow."""
    plan = parse_search_plan_json(
        """
        {
          "field": "semiconductor defect physics",
          "core_terms": ["carrier capture", "nonradiative recombination"],
          "synonyms": {"carrier capture": ["carrier trapping"]},
          "query_options": [
            {
              "label": "defect physics",
              "query": "semiconductor defect physics carrier capture nonradiative recombination",
              "reason": "keeps the field constraint"
            }
          ],
          "recommended_query": "semiconductor defect physics carrier capture nonradiative recombination",
          "confidence": 0.91,
          "notes": "ok"
        }
        """
    )

    assert plan.field == "semiconductor defect physics"
    assert "carrier capture" in plan.core_terms
    assert plan.synonyms["carrier capture"] == ["carrier trapping"]
    assert plan.query_options[0].query.startswith("semiconductor")


def test_fallback_search_plan_uses_manual_field_hint() -> None:
    """Builds a usable manual plan when DeepSeek is unavailable."""
    plan = fallback_search_plan("carrier capture", "semiconductor defect physics")

    assert plan.recommended_query == "semiconductor defect physics carrier capture"
    assert plan.query_options


def test_fallback_search_plan_translates_known_chinese_terms() -> None:
    """Uses local glossary for common Chinese semiconductor terms without DeepSeek."""
    plan = fallback_search_plan("载流子俘获", "半导体物理")

    assert "semiconductor physics" in plan.recommended_query
    assert "carrier capture" in plan.recommended_query
