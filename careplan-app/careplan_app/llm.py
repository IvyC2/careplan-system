import os

import requests
from django.conf import settings


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


def should_use_mock_llm() -> bool:
    # Prefer explicit env override; otherwise default to settings.
    env = os.environ.get("MOCK_LLM")
    if env is not None:
        return env.lower() in ("1", "true", "yes", "on")
    return bool(getattr(settings, "MOCK_LLM", False))


def generate_careplan_text(
    *,
    patient_name: str,
    medication: str,
    diagnosis: str,
    additional_diagnoses: list,
    medication_history: list,
    patient_records: str,
) -> str:
    """
    Generate care plan text via mock or real LLM depending on configuration.
    """
    if should_use_mock_llm():
        return MOCK_CAREPLAN_TEXT

    anthropic_api_key = os.environ.get("CLAUDE_API_KEY")
    if not anthropic_api_key:
        raise RuntimeError("CLAUDE_API_KEY is not set")

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

