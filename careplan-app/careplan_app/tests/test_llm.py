"""
Unit tests for careplan_app.llm — no DB, no network, no Celery.
"""
import pytest
from unittest.mock import patch

from careplan_app.llm import (
    MOCK_CAREPLAN_TEXT,
    BaseLLMService,
    MockService,
    ClaudeService,
    get_llm_service,
)

# ── Common kwargs passed to every .generate() call ───────────────────────────

GENERATE_KWARGS = dict(
    patient_name="John Doe",
    medication="Metformin",
    diagnosis="E11.9",
    additional_diagnoses=["I10"],
    medication_history=["Lisinopril 10mg"],
    patient_records="No known allergies.",
)


# ── MockService ───────────────────────────────────────────────────────────────

def test_mock_service_returns_careplan_text():
    svc = MockService()
    result = svc.generate(**GENERATE_KWARGS)
    assert result == MOCK_CAREPLAN_TEXT


def test_mock_service_result_contains_expected_sections():
    svc = MockService()
    result = svc.generate(**GENERATE_KWARGS)
    for section in ("Problem List:", "Goals:", "Pharmacist Interventions:", "Monitoring Plan:"):
        assert section in result


def test_mock_service_is_base_llm_service():
    assert isinstance(MockService(), BaseLLMService)


# ── get_llm_service() ─────────────────────────────────────────────────────────

def test_get_llm_service_returns_mock_when_env_set():
    with patch.dict("os.environ", {"LLM_PROVIDER": "mock"}):
        svc = get_llm_service()
    assert isinstance(svc, MockService)


def test_get_llm_service_returns_claude_when_env_set():
    with patch.dict("os.environ", {"LLM_PROVIDER": "claude"}):
        svc = get_llm_service()
    assert isinstance(svc, ClaudeService)


def test_get_llm_service_defaults_to_claude_when_env_missing():
    with patch.dict("os.environ", {}, clear=False):
        # Remove LLM_PROVIDER if present so we test the default
        import os
        os.environ.pop("LLM_PROVIDER", None)
        svc = get_llm_service()
    assert isinstance(svc, ClaudeService)


def test_get_llm_service_raises_on_unknown_provider():
    with patch.dict("os.environ", {"LLM_PROVIDER": "gpt-99"}):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm_service()


# ── ClaudeService ─────────────────────────────────────────────────────────────

def test_claude_service_raises_without_api_key():
    svc = ClaudeService()
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(RuntimeError, match="CLAUDE_API_KEY"):
            svc.generate(**GENERATE_KWARGS)
