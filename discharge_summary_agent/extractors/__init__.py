"""
extractors/__init__.py
Core Gemini API plumbing shared by all domain extractors.

Features implemented:
  3. Sliding-window context strategy in get_relevant_content()
  5. JSON schema enforcement via responseSchema in _call_gemini_api_single()
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential


# ---------------------------------------------------------------------------
# Feature 3: Sliding-window context strategy
# ---------------------------------------------------------------------------

def _summarise_page(page_text: str, api_key: str) -> str:
    """
    Compress one page of clinical text to a single sentence using a lightweight
    Gemini call.  Used by get_relevant_content() for pages beyond the top-3.

    Returns a one-sentence summary, or the first 120 chars as a last resort.
    """
    _SUMMARISE_PROMPT = (
        "You are a clinical summarisation assistant. "
        "Summarise the following hospital document page in exactly ONE concise sentence "
        "that preserves all clinically important facts (diagnoses, medications, lab values, dates). "
        "Return ONLY the sentence — no preamble, no JSON."
    )
    try:
        import requests  # type: ignore[import]

        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            "models/gemini-2.5-flash-lite:generateContent"
        )
        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": page_text[:3000]}]}],
            "systemInstruction": {"parts": [{"text": _SUMMARISE_PROMPT}]},
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 120},
        }
        resp = requests.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,   # Phase 3: key in header, not URL
            },
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        pass

    # Last resort: first 120 chars
    return page_text[:120].replace("\n", " ").strip() + " …"


def get_relevant_content(
    content: str,
    extractor_type: str,
    max_chars: int = 9000,
) -> str:
    """
    Sliding-window context strategy:

    1. Parse pages from the full document text.
    2. Score each page for relevance to extractor_type using keyword matching.
    3. Send the top-3 most relevant pages in FULL (up to 4 000 chars each).
    4. Summarise all other relevant pages to 1 sentence each via Gemini.
    5. max_chars acts as a hard ceiling safety net only.

    Public signature is unchanged from the original implementation.
    """
    if not content:
        return ""

    # Parse pages
    pages_raw = content.split("--- PAGE ")
    pages: List[str] = []
    for p in pages_raw:
        if p.strip():
            pages.append("--- PAGE " + p)

    if not pages:
        return ""

    def _page_num(page_str: str) -> int:
        first_line = page_str.split("\n")[0]
        try:
            return int("".join(c for c in first_line if c.isdigit()))
        except Exception:
            return 999

    # Extractor keyword registry
    keywords: Dict[str, List[str]] = {
        "demographics": [
            "name", "age", "sex", "gender", "mrn", "ip number", "ip no",
            "admission date", "discharge date", "blood group", "weight",
        ],
        "diagnoses": [
            "diagnosis", "diagnoses", "history", "complaint", "diagnosed",
            "impression", "history of present illness", "past history",
            "clinical summary",
        ],
        "medications": [
            "medication", "medicine", "drug", "tablet", "tab", "capsule",
            "cap", "injection", "inj", "mg", "twice daily", "once daily",
            "prescription", "discharged on", "admitted on",
        ],
        "labs": [
            "creatinine", "hemoglobin", "hb", "wbc", "platelet", "sodium",
            "potassium", "electrolyte", "urea", "culture", "urine", "blood",
            "lab", "laboratory", "report", "investigations", "crp", "abg",
            "ph", "hco3",
        ],
        "procedures": [
            "procedure", "surgery", "operation", "operated", "underwent",
            "biopsy", "excision", "drainage", "ct", "computed tomography",
            "ultrasound", "usg", "echo", "x-ray", "imaging", "endoscopy",
        ],
        "discharge_info": [
            "discharge", "follow-up", "follow up", "diet", "advice",
            "instructions", "review", "condition", "pending", "stable",
            "prognosis",
        ],
    }

    kws = keywords.get(extractor_type, [])

    def _score(page_str: str) -> int:
        pl = page_str.lower()
        return sum(1 for kw in kws if kw in pl)

    # Pages 1-3 always included (demographics / header context)
    early_pages = [p for p in pages if _page_num(p) <= 3]
    rest = [p for p in pages if _page_num(p) > 3]

    # Score and rank remaining pages
    scored = sorted(rest, key=_score, reverse=True)

    # Determine top-3 by score (early pages already guaranteed)
    top_full: List[str] = list(early_pages)
    surplus: List[str] = []

    for p in scored:
        if _score(p) == 0:
            break                        # no keyword match at all — skip
        if len(top_full) < (3 + len(early_pages)):
            top_full.append(p)
        else:
            surplus.append(p)

    # Fallback: if we still have too few pages, include first 8
    if len(top_full) < 3 and len(pages) > 3:
        for p in pages[:8]:
            if p not in top_full:
                top_full.append(p)

    # Sort all selected pages by page number
    top_full.sort(key=_page_num)

    # Build context: full text for top pages (≤ 4000 chars each)
    parts: List[str] = []
    for p in top_full:
        parts.append(p[:4000])

    # Summarise surplus relevant pages
    if surplus:
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip().strip("'").strip('"')
        for p in surplus:
            if gemini_key:
                summary = _summarise_page(p, gemini_key)
            else:
                # No key — use truncated text
                summary = p[:120].replace("\n", " ").strip() + " …"
            pnum = _page_num(p)
            parts.append(f"--- PAGE {pnum} [SUMMARY] ---\n{summary}")

    result_text = "\n\n".join(parts)

    # Hard ceiling safety net
    if len(result_text) > max_chars:
        result_text = result_text[:max_chars] + "\n\n[TRUNCATED FOR RELEVANCY AND LIMITS]"

    return result_text


# ---------------------------------------------------------------------------
# Feature 5: Gemini API with optional responseSchema
# ---------------------------------------------------------------------------

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=30),
    reraise=True,
)
def _call_gemini_api_single(
    system_prompt: str,
    content_truncated: str,
    api_key: str,
    model_name: str,
    response_schema: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Single Gemini API call with retry logic.

    Args:
        system_prompt     : extraction instruction
        content_truncated : document text already filtered by get_relevant_content()
        api_key           : Gemini API key
        model_name        : e.g. "gemini-2.5-flash-lite"
        response_schema   : optional Gemini Schema dict for responseSchema enforcement.
                            When provided, Gemini is constrained to return exactly
                            the specified field names and types.
    """
    import re
    import requests  # type: ignore[import]

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model_name}:generateContent"
    )

    generation_config: Dict[str, Any] = {
        "responseMimeType": "application/json",
        "temperature": 0.1,
    }

    # Feature 5: inject responseSchema when provided
    if response_schema is not None:
        generation_config["responseSchema"] = response_schema

    payload: Dict[str, Any] = {
        "contents": [{"parts": [{"text": content_truncated}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": generation_config,
    }
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,   # Phase 3: key in header, not URL query param
    }
    response = requests.post(url, json=payload, headers=headers, timeout=60)

    if response.status_code == 429:
        if "Quota exceeded" in response.text or "exceeded your current quota" in response.text:
            raise ValueError(f"Quota Exceeded: {response.text[:200]}")

        msg = response.text
        m = re.search(r"retry in (\d+\.?\d*)", msg)
        sleep_secs = float(m.group(1)) + 5 if m else 30
        time.sleep(min(sleep_secs, 35))
        raise Exception(f"Rate limit (429): {msg[:200]}")

    if response.status_code != 200:
        raise Exception(
            f"Gemini API returned status {response.status_code}: {response.text[:200]}"
        )

    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as e:
        raise Exception(f"Invalid Gemini API response structure: {data}. Error: {e}")


LAST_MODEL_USED = "gemini-2.5-flash-lite"


def _call_gemini_api(
    system_prompt: str,
    content_truncated: str,
    api_key: str,
    response_schema: Optional[Dict[str, Any]] = None,
) -> str:
    global LAST_MODEL_USED  # noqa: PLW0603
    models = ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"]
    last_err: Optional[Exception] = None
    for model in models:
        try:
            res = _call_gemini_api_single(
                system_prompt,
                content_truncated,
                api_key,
                model,
                response_schema=response_schema,
            )
            LAST_MODEL_USED = model
            return res
        except ValueError as e:
            last_err = e
            continue
        except Exception as e:
            last_err = e
            continue
    raise Exception(f"All models failed. Last error: {last_err}")


def extract_with_llm(
    system_prompt: str,
    content: str,
    max_tokens: int = 1500,
    response_schema: Optional[Dict[str, Any]] = None,
) -> dict:
    """
    Base extractor using Google Gemini API.
    Uses JSON mode for reliable structured output.
    Retries up to 3 times with exponential backoff.
    Never raises — returns error dict on failure.

    Args:
        system_prompt   : clinical extraction instruction
        content         : raw document text
        max_tokens      : (reserved for future token budget; currently unused
                          by REST path but kept for API compatibility)
        response_schema : optional Gemini Schema dict to enforce exact field
                          names and types via responseSchema.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return {"error": "api_key_missing", "details": "GEMINI_API_KEY not found in environment"}

    gemini_key = gemini_key.strip().strip("'").strip('"')

    # Infer extractor type from system prompt for keyword-based page filtering
    sys_lower = system_prompt.lower()
    extractor_type = "demographics"  # default fallback
    if "diagnosis" in sys_lower or "diagnoses" in sys_lower:
        extractor_type = "diagnoses"
    elif "medication" in sys_lower or "medications" in sys_lower or "drug" in sys_lower:
        extractor_type = "medications"
    elif (
        "laboratory" in sys_lower
        or "lab" in sys_lower
        or "test" in sys_lower
        or "investigations" in sys_lower
    ):
        extractor_type = "labs"
    elif "procedure" in sys_lower or "procedures" in sys_lower:
        extractor_type = "procedures"
    elif "discharge" in sys_lower or "follow-up" in sys_lower:
        extractor_type = "discharge_info"

    text = ""
    try:
        content_truncated = get_relevant_content(content, extractor_type, max_chars=12000)
        time.sleep(3)  # Throttle: 3 s between calls

        # Inject learned correction rules if available
        try:
            from agent.correction_memory import get_prompt_injection  # type: ignore[import]

            correction_hint = get_prompt_injection(top_n=6)
            if correction_hint:
                system_prompt = system_prompt + correction_hint
        except ImportError:
            pass

        text = _call_gemini_api(
            system_prompt,
            content_truncated,
            gemini_key,
            response_schema=response_schema,
        )
        return json.loads(text)

    except json.JSONDecodeError as e:
        return {"error": "json_parse_failed", "raw_response": text[:500], "details": str(e)}
    except Exception as e:
        return {"error": "api_call_failed", "details": str(e)}
