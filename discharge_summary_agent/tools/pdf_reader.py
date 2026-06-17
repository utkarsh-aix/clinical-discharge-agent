"""
pdf_reader.py
Robust PDF reader with OCR fallback for scanned/image-only pages.

Strategy:
  1. pdfplumber  — fast, extracts text + tables from digital PDFs
  2. Tables → serialised as markdown (### Table N blocks) appended to page text
  3. If image-only → check image_cache dir for pre-rendered PNG
  4. If no cache   → render via pdf2image at 300 DPI
  5. _select_psm() chooses --psm 4 (wide text) or --psm 11 (sparse) automatically
  6. Run pytesseract with chosen PSM; if avg_conf < 60 → EasyOCR fallback
  7. If is_image_only and ocr_confidence < 70 → Gemini Vision multimodal path
  8. If pdfplumber fails entirely → PyPDF2 fallback, then OCR
  9. Never raises — always returns a result dict
"""

from __future__ import annotations

import base64
import io
import os
from typing import Any, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def read_pdf(
    file_path: str,
    ocr: bool = True,
    ocr_dpi: int = 300,
    image_cache_dir: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    vision_system_prompt: Optional[str] = None,
) -> dict:
    """
    Read a PDF and return extracted text per page.

    Args:
        file_path          : path to the PDF
        ocr                : run OCR on image-only pages
        ocr_dpi            : DPI for rendering (ignored when cache hit)
        image_cache_dir    : directory of pre-rendered PNGs named page-NN.png
                             e.g. scratch_ocr/  — skips re-rendering if found
        gemini_api_key     : optional API key for Gemini Vision fallback;
                             falls back to GEMINI_API_KEY env var if None
        vision_system_prompt: optional system prompt for Vision extraction;
                             uses a generic clinical extraction prompt if None

    Returns dict with keys:
        file_path, total_pages, pages, extraction_errors, success, ocr_pages
    """
    result: dict = {
        "file_path": file_path,
        "total_pages": 0,
        "pages": [],
        "extraction_errors": [],
        "success": False,
        "ocr_pages": 0,
    }

    if not os.path.exists(file_path):
        result["extraction_errors"].append(f"File not found: {file_path}")
        return result

    # Resolve Gemini key once so we don't re-read env on every Vision call
    _gemini_key: Optional[str] = (
        gemini_api_key
        or os.getenv("GEMINI_API_KEY", "").strip().strip("'").strip('"')
        or None
    )

    try:
        import pdfplumber

        with pdfplumber.open(file_path) as pdf:
            result["total_pages"] = len(pdf.pages)

            for i, page in enumerate(pdf.pages):
                page_data: dict = {
                    "page_number": i + 1,
                    "text": "",
                    "tables": [],
                    "is_image_only": False,
                    "extraction_method": "pdfplumber",
                    "ocr_confidence": None,
                }

                try:
                    text: str = page.extract_text() or ""
                    raw_tables: List[Any] = page.extract_tables() or []
                    page_data["tables"] = raw_tables

                    # ── Feature 1: append markdown tables to page text ──────
                    if raw_tables:
                        table_md = _tables_to_markdown(raw_tables)
                        if table_md:
                            text = text + "\n\n" + table_md

                    if len(text.strip()) < 20:          # image-only page
                        page_data["is_image_only"] = True
                        if ocr:
                            img = _render_page(file_path, i, ocr_dpi, image_cache_dir)
                            ocr_text, ocr_conf = _ocr_page(
                                file_path, i, ocr_dpi, image_cache_dir, img
                            )

                            # ── Feature 4: Gemini Vision if conf still low ──
                            if (
                                ocr_conf < 70
                                and _gemini_key
                                and img is not None
                            ):
                                vision_text = _ocr_page_vision(
                                    img,
                                    api_key=_gemini_key,
                                    system_prompt=vision_system_prompt,
                                )
                                if vision_text and len(vision_text.strip()) > 10:
                                    page_data["text"] = vision_text
                                    page_data["extraction_method"] = "gemini_vision"
                                    page_data["ocr_confidence"] = 85.0  # Vision path — high proxy
                                    result["ocr_pages"] += 1
                                    result["pages"].append(page_data)
                                    continue

                            if ocr_text and len(ocr_text.strip()) > 10:
                                page_data["text"] = ocr_text
                                page_data["extraction_method"] = (
                                    "easyocr_fallback"
                                    if ocr_conf < 60
                                    else "tesseract_ocr"
                                )
                                page_data["ocr_confidence"] = ocr_conf
                                result["ocr_pages"] += 1
                            else:
                                page_data["text"] = "[PAGE: NO TEXT READABLE BY OCR]"
                                page_data["ocr_confidence"] = 0.0
                        else:
                            page_data["text"] = "[IMAGE-ONLY PAGE — OCR DISABLED]"
                    else:
                        page_data["text"] = text
                        page_data["ocr_confidence"] = 100.0  # digital page — perfect

                except Exception as e:
                    page_data["is_image_only"] = True
                    page_data["text"] = "[PAGE EXTRACTION ERROR]"
                    result["extraction_errors"].append(f"Page {i + 1}: {e}")

                result["pages"].append(page_data)

        result["success"] = True

    except Exception as outer_err:
        result["extraction_errors"].append(f"pdfplumber failed: {outer_err}")
        # PyPDF2 fallback
        try:
            import PyPDF2

            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                result["total_pages"] = len(reader.pages)
                for i, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    is_image = len(text.strip()) < 20
                    ocr_text = ""
                    ocr_conf: float = 0.0
                    if is_image and ocr:
                        ocr_text, ocr_conf = _ocr_page(
                            file_path, i, ocr_dpi, image_cache_dir
                        )
                    result["pages"].append(
                        {
                            "page_number": i + 1,
                            "text": ocr_text if ocr_text else (text or "[NO TEXT]"),
                            "tables": [],
                            "is_image_only": is_image,
                            "extraction_method": "pypdf2_ocr" if ocr_text else "pypdf2",
                            "ocr_confidence": ocr_conf if is_image else None,
                        }
                    )
                    if ocr_text:
                        result["ocr_pages"] += 1
            result["success"] = True
        except Exception as e2:
            result["extraction_errors"].append(f"PyPDF2 also failed: {e2}")

    return result


def get_full_text(result: dict, max_chars_per_page: int = 3000) -> str:
    """
    Concatenate all page texts into a single string.
    Caps each page at max_chars_per_page to avoid context explosion.
    Placeholder-only pages are skipped.
    """
    parts: List[str] = []
    for p in result.get("pages", []):
        text = p.get("text", "").strip()
        if not text:
            continue
        # Skip pure placeholder lines
        if text.startswith("[") and text.endswith("]"):
            continue
        parts.append(f"--- PAGE {p['page_number']} ---\n{text[:max_chars_per_page]}")
    return "\n\n".join(parts)


def get_ocr_stats(result: dict) -> dict:
    """Return a summary of extraction stats for logging."""
    total = result.get("total_pages", 0)
    ocr = result.get("ocr_pages", 0)
    image_only = sum(1 for p in result.get("pages", []) if p.get("is_image_only"))
    text_chars = sum(
        len(p.get("text", ""))
        for p in result.get("pages", [])
        if not p.get("text", "").startswith("[")
    )
    conf_scores = [
        p["ocr_confidence"]
        for p in result.get("pages", [])
        if p.get("ocr_confidence") is not None
    ]
    avg_conf = round(sum(conf_scores) / len(conf_scores), 1) if conf_scores else 100.0
    return {
        "total_pages": total,
        "image_only_pages": image_only,
        "ocr_pages": ocr,
        "digital_pages": total - image_only,
        "total_text_chars": text_chars,
        "avg_chars_per_page": text_chars // max(ocr + (total - image_only), 1),
        "avg_ocr_confidence": avg_conf,
    }


# ---------------------------------------------------------------------------
# Feature 1: Table → Markdown serialisation
# ---------------------------------------------------------------------------

def _tables_to_markdown(tables: List[List[List[Any]]]) -> str:
    """
    Convert pdfplumber nested-list tables to GitHub-flavoured markdown tables.

    Each table is rendered with:
      ### Table N
      | col1 | col2 | ...
      |------|------|----
      | val  | val  | ...

    None cells are replaced with empty string.
    Uses tabulate if available; falls back to manual string formatting.
    """
    if not tables:
        return ""

    blocks: List[str] = []

    for n, table in enumerate(tables, start=1):
        if not table:
            continue

        # Sanitise: replace None and strip whitespace
        clean_rows: List[List[str]] = []
        for row in table:
            if row is None:
                continue
            clean_rows.append(
                [str(cell).strip() if cell is not None else "" for cell in row]
            )

        if not clean_rows:
            continue

        heading = f"### Table {n}"

        try:
            from tabulate import tabulate  # type: ignore[import]

            md_table = tabulate(
                clean_rows[1:] if len(clean_rows) > 1 else clean_rows,
                headers=clean_rows[0] if len(clean_rows) > 1 else [],
                tablefmt="github",
            )
            blocks.append(f"{heading}\n{md_table}")

        except ImportError:
            # Manual fallback — no tabulate required
            header = clean_rows[0]
            data_rows = clean_rows[1:]
            # Column widths
            col_widths = [max(len(h), 3) for h in header]
            for row in data_rows:
                for ci, cell in enumerate(row):
                    if ci < len(col_widths):
                        col_widths[ci] = max(col_widths[ci], len(cell))

            def _fmt_row(cells: List[str]) -> str:
                padded = [
                    cells[ci].ljust(col_widths[ci]) if ci < len(col_widths) else cells[ci]
                    for ci in range(len(cells))
                ]
                return "| " + " | ".join(padded) + " |"

            sep = "| " + " | ".join("-" * w for w in col_widths) + " |"
            lines = [heading, _fmt_row(header), sep]
            for row in data_rows:
                # Pad short rows with empty strings
                padded_row = row + [""] * (len(header) - len(row))
                lines.append(_fmt_row(padded_row[: len(header)]))
            blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Feature 2 helper: PSM selector
# ---------------------------------------------------------------------------

def _select_psm(img: Any, page_width_px: Optional[float] = None) -> int:
    """
    Choose Tesseract PSM based on the layout of detected text boxes.

    Decision rule:
    - Get word bounding boxes from pytesseract
    - Compute the fraction of page width spanned by the combined bbox x-range
    - If > 80 % → single-column layout → PSM 4 (single column of text)
    - Else       → sparse/multi-column  → PSM 11 (sparse text)

    Falls back to PSM 6 (uniform block) if pytesseract is unavailable.
    """
    try:
        import pytesseract
        from PIL import Image as PILImage

        img_width = img.width if hasattr(img, "width") else (page_width_px or 1)

        # Quick bounding-box scan with psm 3 (auto detect, cheap)
        data = pytesseract.image_to_data(
            img,
            output_type=pytesseract.Output.DICT,
            config="--psm 3 --oem 3",
        )
        lefts = [
            data["left"][i]
            for i in range(len(data["text"]))
            if str(data["text"][i]).strip() and data["conf"][i] > 0
        ]
        rights = [
            data["left"][i] + data["width"][i]
            for i in range(len(data["text"]))
            if str(data["text"][i]).strip() and data["conf"][i] > 0
        ]
        if not lefts:
            return 6  # nothing found — use safe default

        x_span = max(rights) - min(lefts)
        span_fraction = x_span / img_width

        if span_fraction > 0.80:
            return 4   # single wide column (typical typed clinical doc)
        else:
            return 11  # sparse / multi-column (stamps, scattered elements)

    except Exception:
        return 6  # safe fallback


# ---------------------------------------------------------------------------
# Feature 4 helper: Gemini Vision multimodal path
# ---------------------------------------------------------------------------

def _ocr_page_vision(
    img: Any,
    api_key: str,
    system_prompt: Optional[str] = None,
) -> str:
    """
    Send a PIL image to Gemini Vision (gemini-1.5-pro) as an inline base64
    image part and return extracted clinical text.

    Used when is_image_only=True and Tesseract/EasyOCR confidence < 70.

    Args:
        img          : PIL Image of the rendered PDF page
        api_key      : Gemini API key
        system_prompt: custom extraction instruction (optional)

    Returns extracted text string, or "" on failure.
    """
    _DEFAULT_VISION_PROMPT = (
        "You are a senior medical document analyst. "
        "The image below is a scanned page from a hospital discharge summary. "
        "Extract ALL text exactly as written — including handwriting, stamps, "
        "lab values, medication names, dates, and dosages. "
        "Preserve line structure. Do not paraphrase or omit any content. "
        "Return plain text only, no JSON."
    )

    try:
        import requests

        prompt = system_prompt or _DEFAULT_VISION_PROMPT

        # Convert PIL image to base64 JPEG
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=90)
        b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/gemini-1.5-pro:generateContent?key={api_key}"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_data,
                            }
                        },
                        {"text": "Extract all text from this clinical document page."},
                    ]
                }
            ],
            "systemInstruction": {"parts": [{"text": prompt}]},
            "generationConfig": {"temperature": 0.0},
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=90)

        if response.status_code != 200:
            return ""

        data = response.json()
        return (
            data["candidates"][0]["content"]["parts"][0]["text"].strip()
        )

    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Internal OCR helpers
# ---------------------------------------------------------------------------

def _render_page(
    file_path: str,
    page_index: int,
    dpi: int = 300,
    image_cache_dir: Optional[str] = None,
) -> Optional[Any]:
    """
    Render a PDF page to a PIL Image. Checks cache first.
    Returns PIL Image or None on failure.
    """
    try:
        from PIL import Image as PILImage

        # Try cached image
        if image_cache_dir and os.path.isdir(image_cache_dir):
            page_num = page_index + 1
            candidates = [
                os.path.join(image_cache_dir, f"page-{page_num:02d}.png"),
                os.path.join(image_cache_dir, f"page-{page_num:03d}.png"),
                os.path.join(image_cache_dir, f"page-{page_num}.png"),
            ]
            for c in candidates:
                if os.path.exists(c):
                    return PILImage.open(c)

        # Render fresh
        from pdf2image import convert_from_path  # type: ignore[import]

        images = convert_from_path(
            file_path,
            dpi=dpi,
            first_page=page_index + 1,
            last_page=page_index + 1,
            fmt="jpeg",
        )
        return images[0] if images else None

    except Exception:
        return None


def _ocr_page(
    file_path: str,
    page_index: int,
    dpi: int = 300,
    image_cache_dir: Optional[str] = None,
    img: Optional[Any] = None,
) -> Tuple[str, float]:
    """
    OCR a single PDF page with a two-path strategy:

    Path A — pytesseract
      - _select_psm() chooses --psm 4 (wide text column) or
        --psm 11 (sparse/scattered elements)
      - Confidence-scored via image_to_data

    Path B — EasyOCR fallback (when Tesseract avg_conf < 60)
      - Uses 'en' language model, GPU auto-detected

    Cache priority (before any rendering):
      1. Pre-extracted .txt file in image_cache_dir
      2. Pre-rendered .png in image_cache_dir
      3. Fresh render via pdf2image

    Returns:
        (text, avg_confidence) — text may be "" on total failure
    """
    try:
        import pytesseract  # type: ignore[import]

        # ── 1. Try cached text file ─────────────────────────────────────────
        if image_cache_dir and os.path.isdir(image_cache_dir):
            page_num = page_index + 1
            txt_candidates = [
                os.path.join(image_cache_dir, f"page-{page_num:02d}.txt"),
                os.path.join(image_cache_dir, f"page-{page_num:03d}.txt"),
                os.path.join(image_cache_dir, f"page-{page_num}.txt"),
            ]
            for c in txt_candidates:
                if os.path.exists(c):
                    with open(c, "r", encoding="utf-8") as fh:
                        cached_text = fh.read().strip()
                    # Cached text has no confidence score — return 80 as proxy
                    return cached_text, 80.0

        # ── 2. Obtain / reuse rendered image ───────────────────────────────
        if img is None:
            img = _render_page(file_path, page_index, dpi, image_cache_dir)
        if img is None:
            return "", 0.0

        # ── 3. Choose PSM based on layout ──────────────────────────────────
        psm = _select_psm(img)
        tess_config = f"--psm {psm} --oem 3"

        # ── 4. Run Tesseract with confidence scoring ────────────────────────
        data = pytesseract.image_to_data(
            img,
            output_type=pytesseract.Output.DICT,
            config=tess_config,
        )
        word_confs = [
            float(data["conf"][i])
            for i in range(len(data["text"]))
            if data["conf"][i] != -1 and str(data["text"][i]).strip() != ""
        ]
        avg_conf = round(sum(word_confs) / len(word_confs), 1) if word_confs else 0.0

        # Group words by (block, paragraph, line) — once-through reconstruction
        lines: dict = {}
        for i in range(len(data["text"])):
            w = str(data["text"][i])
            if data["conf"][i] != -1:
                key = (
                    data["block_num"][i],
                    data["par_num"][i],
                    data["line_num"][i],
                )
                lines.setdefault(key, []).append(w)

        line_texts = [
            " ".join(w.strip() for w in lines[k] if w.strip())
            for k in sorted(lines)
        ]
        tess_text = "\n".join(t for t in line_texts if t).strip()

        # ── 5. EasyOCR fallback when Tesseract confidence < 60 ─────────────
        if avg_conf < 60:
            easy_text, easy_conf = _easyocr_fallback(img)
            if easy_text and len(easy_text.strip()) > len(tess_text.strip()):
                return easy_text, easy_conf
            # If EasyOCR also failed, return Tesseract result with original conf
            return tess_text, avg_conf

        return tess_text, avg_conf

    except Exception:
        return "", 0.0


def _easyocr_fallback(img: Any) -> Tuple[str, float]:
    """
    EasyOCR fallback for low-confidence Tesseract pages.

    Uses the 'en' (English) reader. GPU is auto-detected by EasyOCR.
    Reader instance is module-level cached to avoid repeated init cost.

    Returns:
        (text, avg_confidence_0_to_100)
    """
    global _EASYOCR_READER  # noqa: PLW0603

    try:
        import easyocr  # type: ignore[import]
        import numpy as np  # type: ignore[import]

        if _EASYOCR_READER is None:
            # verbose=False suppresses download progress bars in production
            _EASYOCR_READER = easyocr.Reader(["en"], verbose=False)

        # EasyOCR expects a numpy array or file path
        img_array = np.array(img)
        results = _EASYOCR_READER.readtext(img_array)

        if not results:
            return "", 0.0

        lines_out: List[str] = []
        confs: List[float] = []
        for (_bbox, text, conf) in results:
            if text.strip():
                lines_out.append(text.strip())
                confs.append(conf * 100.0)  # normalise to 0-100 scale

        avg_conf = round(sum(confs) / len(confs), 1) if confs else 0.0
        return "\n".join(lines_out), avg_conf

    except ImportError:
        # easyocr not installed — degrade gracefully
        return "", 0.0
    except Exception:
        return "", 0.0


# Module-level EasyOCR reader cache (avoids repeated model loading)
_EASYOCR_READER: Optional[Any] = None
