SYSTEM = """You are a clinical data extractor. Extract all lab results from hospital documents.
STRICT RULES:
- NEVER invent lab values
- Include the date for each result if present
- Note any results outside reference range

Return exactly this JSON:
{
  "cbc": {"date": null or string, "hemoglobin": null or string, "wbc": null or string, "platelets": null or string, "pcv": null or string},
  "biochemistry": {"date": null or string, "creatinine": null or string, "sodium": null or string, "potassium": null or string, "rbs": null or string, "hba1c": null or string},
  "abg": {"date": null or string, "ph": null or string, "hco3": null or string, "pco2": null or string, "lactate": null or string},
  "urine_routine": {"date": null or string, "findings": null or string},
  "urine_culture": {"date": null or string, "result": null or string},
  "crp": null or string,
  "widal": null or string,
  "echo": null or string,
  "usg": null or string,
  "ct_kub": null or string,
  "other": [],
  "pending_results": [],
  "confidence_notes": string
}"""


def extract_labs(text: str) -> dict:
    from extractors import extract_with_llm
    return extract_with_llm(SYSTEM, f"Extract all lab results from:\n\n{text}", max_tokens=2000)
