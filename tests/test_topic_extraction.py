"""Tests for Abstract-based topic extraction."""

from app.topic_extraction import extract_abstract, extract_keywords_from_abstract


def test_extract_abstract_between_headings() -> None:
    """Extracts Abstract content before Introduction."""
    text = """
    Title

    Abstract
    Retrieval augmented generation combines neural language models with external
    knowledge retrieval for grounded question answering systems. Retrieval quality
    and document ranking strongly affect generation reliability.

    1 Introduction
    The rest of the paper starts here.
    """

    abstract = extract_abstract(text)

    assert abstract is not None
    assert "Retrieval augmented generation" in abstract
    assert "The rest of the paper" not in abstract


def test_extract_abstract_returns_none_when_too_short() -> None:
    """Avoids treating tiny heading fragments as usable abstracts."""
    assert extract_abstract("Abstract\nShort text.\nIntroduction\nBody") is None


def test_extract_abstract_when_heading_is_inline() -> None:
    """Extracts abstracts from common inline PDF text."""
    text = (
        "A Paper Title ABSTRACT - Multiphonon nonradiative carrier capture in "
        "semiconductors is a central process controlling defect recombination. "
        "We analyze carrier trapping, electron phonon coupling, configuration "
        "coordinate diagrams, capture coefficients, and defect levels using "
        "first-principles calculations for wide bandgap materials. Keywords: "
        "carrier trapping; nonradiative recombination"
    )

    abstract = extract_abstract(text)

    assert abstract is not None
    assert "carrier capture" in abstract
    assert "Keywords" not in abstract


def test_extract_abstract_supports_chinese_headings() -> None:
    """Extracts abstracts with Chinese headings."""
    text = (
        "题目\n摘要：本文讨论半导体缺陷中的非辐射载流子俘获过程，"
        "重点分析多声子发射、电子声子耦合、构型坐标图、俘获系数和缺陷能级。"
        "这些机制对于宽禁带材料的复合中心和器件可靠性具有重要意义。"
        "关键词：载流子俘获；非辐射复合\n引言\n正文"
    )

    abstract = extract_abstract(text)

    assert abstract is not None
    assert "非辐射载流子俘获" in abstract


def test_extract_keywords_from_abstract_prefers_repeated_terms() -> None:
    """Ranks repeated abstract terms and phrases."""
    abstract = (
        "Graph neural networks improve molecular property prediction. "
        "Graph neural networks use message passing for molecular graphs. "
        "Molecular property prediction benefits from graph representations."
    )

    keywords = extract_keywords_from_abstract(abstract, max_keywords=5)

    assert "graph neural" in keywords
    assert "molecular property" in keywords
