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


def test_extract_keywords_from_abstract_prefers_repeated_terms() -> None:
    """Ranks repeated abstract terms and phrases."""
    abstract = (
        "Graph neural networks improve molecular property prediction. "
        "Graph neural networks use message passing for molecular graphs. "
        "Molecular property prediction benefits from graph representations."
    )

    keywords = extract_keywords_from_abstract(abstract, max_keywords=5)

    assert "graph neural" in keywords
    assert "molecular" in keywords

