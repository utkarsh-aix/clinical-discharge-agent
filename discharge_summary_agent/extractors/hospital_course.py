"""
extractors/hospital_course.py
Hospital course narrative extractor with Gemini responseSchema enforcement.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Feature 5: Gemini JSON Schema
# ---------------------------------------------------------------------------
_KEY_EVENT_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "date":  {"type": "STRING", "nullable": True},
        "event": {"type": "STRING"},
    },
    "required": ["date", "event"],
}

RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "hospital_course":        {"type": "STRING", "nullable": True},
        "key_events":             {"type": "ARRAY", "items": _KEY_EVENT_SCHEMA},
        "response_to_treatment":  {"type": "STRING", "nullable": True},
        "confidence_notes":       {"type": "STRING"},
    },
    "required": [
        "hospital_course", "key_events",
        "response_to_treatment", "confidence_notes",
    ],
}

SYSTEM = """You are a clinical data extractor. Extract the hospital course narrative from hospital documents.
STRICT RULES:
- NEVER fabricate, invent, or summarize beyond what is explicitly written in the notes
- Extract ONLY what is documented in progress notes, clinical summaries, or admission notes
- If course details are spread across multiple notes, combine them chronologically
- Do NOT fill gaps with assumptions or plausible values
- If no hospital course narrative is found, return null — do not guess

Return exactly this JSON:
{
  "hospital_course": null or string,
  "key_events": [
    {"date": null or string, "event": string}
  ],
  "response_to_treatment": null or string,
  "confidence_notes": string
}"""


def extract_hospital_course(text: str) -> dict:
    from extractors import extract_with_llm
    return extract_with_llm(
        SYSTEM,
        f"Extract the hospital course narrative from these clinical notes:\n\n{text}",
        max_tokens=2000,
        response_schema=RESPONSE_SCHEMA,
    )
