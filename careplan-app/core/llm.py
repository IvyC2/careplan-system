import os
import requests
from abc import ABC, abstractmethod


MOCK_CAREPLAN_TEXT = """\
Problem List:
- Type 2 diabetes mellitus
- Hypertension

Goals:
- Improve glycemic control (A1c individualized)
- Maintain blood pressure within target range

Pharmacist Interventions:
- Review adherence and adverse effects
- Provide lifestyle counseling (diet, activity)
- Medication reconciliation and optimization recommendations

Monitoring Plan:
- Check A1c every 3 months until stable
- Home BP monitoring 3-4x/week
- Watch for hypoglycemia symptoms
"""


class BaseLLMService(ABC):

    @abstractmethod
    def generate(self, *, patient_name, medication, diagnosis,
                 additional_diagnoses, medication_history, patient_records) -> str:
        pass


class MockService(BaseLLMService):

    def generate(self, *, patient_name, medication, diagnosis,
                 additional_diagnoses, medication_history, patient_records) -> str:
        return MOCK_CAREPLAN_TEXT


class ClaudeService(BaseLLMService):

    def generate(self, *, patient_name, medication, diagnosis,
                 additional_diagnoses, medication_history, patient_records) -> str:
        # LLM_API_KEY (Lambda convention) takes precedence; fall back to CLAUDE_API_KEY (Django convention)
        anthropic_api_key = os.environ.get("LLM_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        if not anthropic_api_key:
            raise RuntimeError("LLM_API_KEY (or CLAUDE_API_KEY) is not set")

        prompt = f"""
Generate a care plan for the following patient:
Patient: {patient_name}
Medication: {medication}
Primary Diagnosis: {diagnosis}
Additional Diagnoses: {', '.join(additional_diagnoses) if additional_diagnoses else 'None'}
Medication History: {', '.join(medication_history) if medication_history else 'None'}
Patient Records: {patient_records or 'None'}

Please include these sections:
Problem List:
Goals:
Pharmacist Interventions:
Monitoring Plan:

Important: Use only basic ASCII characters. Do not use special characters like em-dashes (--),
smart quotes, or any unicode characters. Use regular hyphens (-) and straight quotes instead.
"""
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-5",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        response.raise_for_status()

        result = response.json()
        careplan_text = result["content"][0]["text"]
        return careplan_text.encode("ascii", errors="replace").decode("ascii")


def get_llm_service() -> BaseLLMService:
    providers = {
        "claude": ClaudeService(),
        "mock": MockService(),
    }
    provider_name = os.environ.get("LLM_PROVIDER", "claude")
    if provider_name not in providers:
        raise ValueError(f"Unknown LLM provider: {provider_name}")
    return providers[provider_name]