SYSTEM = """You are a clinical data extractor. Extract all medications from hospital documents.
STRICT RULES:
- NEVER invent medication names, doses, or frequencies
- If dose is not documented, return null for that field - do not guess
- Capture admission meds, inpatient meds, and discharge meds separately

Return exactly this JSON:
{
  "admission_medications": [
    {"name": string, "dose": null or string, "route": null or string, "frequency": null or string}
  ],
  "inpatient_medications": [
    {"name": string, "dose": null or string, "route": null or string, "frequency": null or string, "dates": null or string}
  ],
  "discharge_medications": [
    {"name": string, "dose": null or string, "route": null or string, "frequency": null or string, "duration": null or string}
  ],
  "pre_admission_medications": [
    {"name": string, "notes": string}
  ],
  "confidence_notes": string
}"""


def extract_medications(text: str) -> dict:
    from extractors import extract_with_llm
    return extract_with_llm(SYSTEM, f"Extract all medications from:\n\n{text}", max_tokens=2000)
