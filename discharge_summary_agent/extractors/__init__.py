import os
import json
import time
from tenacity import retry, stop_after_attempt, wait_exponential

def get_relevant_content(content: str, extractor_type: str, max_chars: int = 9000) -> str:
    """Filter document content to only send pages relevant to the extractor type."""
    if not content:
        return ""

    pages_raw = content.split("--- PAGE ")
    pages = []
    # Reconstruct pages with page header
    for p in pages_raw:
        if not p.strip():
            continue
        pages.append("--- PAGE " + p)

    relevant_pages = []

    # 1. Always include pages 1-3 as they usually contain demographics and initial details
    for p in pages:
        first_line = p.split("\n")[0]
        try:
            p_num = int("".join(c for c in first_line if c.isdigit()))
            if p_num <= 3:
                relevant_pages.append(p)
        except Exception:
            pass

    # 2. Extractor specific keywords
    keywords = {
        "demographics": ["name", "age", "sex", "gender", "mrn", "ip number", "ip no", "admission date", "discharge date", "blood group", "weight"],
        "diagnoses": ["diagnosis", "diagnoses", "history", "complaint", "diagnosed", "impression", "history of present illness", "past history", "clinical summary"],
        "medications": ["medication", "medicine", "drug", "tablet", "tab", "capsule", "cap", "injection", "inj", "mg", "twice daily", "once daily", "prescription", "discharged on", "admitted on"],
        "labs": ["creatinine", "hemoglobin", "hb", "wbc", "platelet", "sodium", "potassium", "electrolyte", "urea", "culture", "urine", "blood", "lab", "laboratory", "report", "investigations", "crp", "abg", "ph", "hco3"],
        "procedures": ["procedure", "surgery", "operation", "operated", "underwent", "biopsy", "excision", "drainage", "ct", "computed tomography", "ultrasound", "usg", "echo", "x-ray", "imaging", "endoscopy"],
        "discharge_info": ["discharge", "follow-up", "follow up", "diet", "advice", "instructions", "review", "condition", "pending", "stable", "prognosis"]
    }

    kws = keywords.get(extractor_type, [])

    for p in pages:
        if p in relevant_pages:
            continue
        p_lower = p.lower()
        if any(kw in p_lower for kw in kws):
            relevant_pages.append(p)

    # If too few pages found, fall back to first few pages
    if len(relevant_pages) <= 3 and len(pages) > 3:
        for p in pages[:8]:
            if p not in relevant_pages:
                relevant_pages.append(p)

    # Sort pages by page number to keep order
    def get_page_num(page_str):
        first_line = page_str.split("\n")[0]
        try:
            return int("".join(c for c in first_line if c.isdigit()))
        except Exception:
            return 999

    relevant_pages.sort(key=get_page_num)

    # Concatenate and truncate to max_chars
    result_text = "\n\n".join(relevant_pages)
    if len(result_text) > max_chars:
        result_text = result_text[:max_chars] + "\n\n[TRUNCATED FOR RELEVANCY AND LIMITS]"
    return result_text


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=15))
def _call_gemini_api(system_prompt: str, content_truncated: str, api_key: str) -> str:
    import requests
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": content_truncated}
                ]
            }
        ],
        "systemInstruction": {
            "parts": [
                {"text": system_prompt}
            ]
        },
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1
        }
    }
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    if response.status_code != 200:
        raise Exception(f"Gemini API returned status {response.status_code}: {response.text}")
    
    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as e:
        raise Exception(f"Invalid Gemini API response structure: {data}. Error: {e}")


def extract_with_llm(system_prompt: str, content: str, max_tokens: int = 1500) -> dict:
    """
    Base extractor using Google Gemini API.
    Uses JSON mode for reliable structured output.
    Retries up to 3 times with exponential backoff.
    Never raises - returns error dict on failure.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return {"error": "api_key_missing", "details": "GEMINI_API_KEY not found in environment"}

    gemini_key = gemini_key.strip().strip("'").strip('"')

    # Determine the extractor type based on the system prompt
    sys_lower = system_prompt.lower()
    extractor_type = "demographics"  # default fallback
    if "diagnosis" in sys_lower or "diagnoses" in sys_lower:
        extractor_type = "diagnoses"
    elif "medication" in sys_lower or "medications" in sys_lower or "drug" in sys_lower:
        extractor_type = "medications"
    elif "laboratory" in sys_lower or "lab" in sys_lower or "test" in sys_lower or "investigations" in sys_lower:
        extractor_type = "labs"
    elif "procedure" in sys_lower or "procedures" in sys_lower:
        extractor_type = "procedures"
    elif "discharge" in sys_lower or "follow-up" in sys_lower:
        extractor_type = "discharge_info"

    text = ""
    try:
        # Gemini can accept much larger context safely
        content_truncated = get_relevant_content(content, extractor_type, max_chars=80000)
        text = _call_gemini_api(system_prompt, content_truncated, gemini_key)
        return json.loads(text)

    except json.JSONDecodeError as e:
        return {"error": "json_parse_failed", "raw_response": text[:500], "details": str(e)}
    except Exception as e:
        return {"error": "api_call_failed", "details": str(e)}
