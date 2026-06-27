"""Smoke tests for Masterv2 v2.1 extraction prompt."""
from claude_analyzer import EXTRACTION_PROMPT


def test_prompt_has_v21_keys():
    assert "cross_references" in EXTRACTION_PROMPT
    assert "table_purpose" in EXTRACTION_PROMPT
    assert "pipe_runs" in EXTRACTION_PROMPT
    assert "civil_structures" in EXTRACTION_PROMPT
    assert "specification_reference" in EXTRACTION_PROMPT


def test_prompt_has_classification_rules():
    assert "TABLE CLASSIFICATION" in EXTRACTION_PROMPT or "RULES" in EXTRACTION_PROMPT
    assert "CIVIL STRUCTURES" in EXTRACTION_PROMPT or "civil_structures" in EXTRACTION_PROMPT
