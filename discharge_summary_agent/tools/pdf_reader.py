"""
pdf_reader.py
Robust PDF reader with OCR fallback for scanned/image-only pages.

Strategy:
  1. pdfplumber  — fast, extracts text from digital PDFs
  2. If image-only → check image_cache dir for pre-rendered PNG
  3. If no cache   → render via pdf2image at 300 DPI
  4. Run pytesseract on the image
  5. If pdfplumber fails entirely → PyPDF2 fallback, then OCR
  6. Never raises — always returns a result dict
"""

import os


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def read_pdf(file_path: str,
             ocr: bool = True,
             ocr_dpi: int = 300,
             image_cache_dir: str = None) -> dict:
    """
    Read a PDF and return extracted text per page.

    Args:
        file_path       : path to the PDF
        ocr             : run OCR on image-only pages
        ocr_dpi         : DPI for rendering (ignored when cache hit)
        image_cache_dir : directory of pre-rendered PNGs named page-NN.png
                          e.g. scratch_ocr/  — skips re-rendering if found

    Returns dict with keys:
        file_path, total_pages, pages, extraction_errors, success, ocr_pages
    """
    result = {
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

    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            result["total_pages"] = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                page_data = {
                    "page_number": i + 1,
                    "text": "",
                    "tables": [],
                    "is_image_only": False,
                    "extraction_method": "pdfplumber",
                    "ocr_confidence": None,
                }
                try:
                    text = page.extract_text() or ""
                    tables = page.extract_tables() or []
                    page_data["tables"] = tables

                    if len(text.strip()) < 20:          # image-only page
                        page_data["is_image_only"] = True
                        if ocr:
                            ocr_text = _ocr_page(
                                file_path, i, ocr_dpi, image_cache_dir
                            )
                            if ocr_text and len(ocr_text.strip()) > 10:
                                page_data["text"] = ocr_text
                                page_data["extraction_method"] = "tesseract_ocr"
                                result["ocr_pages"] += 1
                            else:
                                page_data["text"] = "[PAGE: NO TEXT READABLE BY OCR]"
                        else:
                            page_data["text"] = "[IMAGE-ONLY PAGE — OCR DISABLED]"
                    else:
                        page_data["text"] = text

                except Exception as e:
                    page_data["is_image_only"] = True
                    page_data["text"] = "[PAGE EXTRACTION ERROR]"
                    result["extraction_errors"].append(f"Page {i+1}: {e}")

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
                    if is_image and ocr:
                        ocr_text = _ocr_page(
                            file_path, i, ocr_dpi, image_cache_dir
                        )
                    result["pages"].append({
                        "page_number": i + 1,
                        "text": ocr_text if ocr_text else (text or "[NO TEXT]"),
                        "tables": [],
                        "is_image_only": is_image,
                        "extraction_method": "pypdf2_ocr" if ocr_text else "pypdf2",
                        "ocr_confidence": None,
                    })
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
    parts = []
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
    return {
        "total_pages": total,
        "image_only_pages": image_only,
        "ocr_pages": ocr,
        "digital_pages": total - image_only,
        "total_text_chars": text_chars,
        "avg_chars_per_page": text_chars // max(ocr + (total - image_only), 1),
    }


# ---------------------------------------------------------------------------
# Internal OCR helper
# ---------------------------------------------------------------------------

def _ocr_page(file_path: str,
              page_index: int,
              dpi: int = 300,
              image_cache_dir: str = None) -> str:
    """
    OCR a single PDF page.
    1. Check image_cache_dir for page-NN.png (zero-padded, 1-indexed)
    2. If not found, render via pdf2image
    3. Run pytesseract on the PIL image
    Returns extracted text or "" on failure.
    """
    try:
        import pytesseract
        from PIL import Image

        img = None

        # ── 1. Try cached text file first ───────────────────────────────────
        if image_cache_dir and os.path.isdir(image_cache_dir):
            page_num = page_index + 1
            txt_candidates = [
                os.path.join(image_cache_dir, f"page-{page_num:02d}.txt"),
                os.path.join(image_cache_dir, f"page-{page_num:03d}.txt"),
                os.path.join(image_cache_dir, f"page-{page_num}.txt"),
            ]
            for c in txt_candidates:
                if os.path.exists(c):
                    with open(c, "r", encoding="utf-8") as f:
                        return f.read().strip()

        # ── 2. Try cache image second ─────────────────────────────────────
        if image_cache_dir and os.path.isdir(image_cache_dir):
            page_num = page_index + 1
            # Try both zero-padded (page-01.png) and plain (page-1.png)
            candidates = [
                os.path.join(image_cache_dir, f"page-{page_num:02d}.png"),
                os.path.join(image_cache_dir, f"page-{page_num:03d}.png"),
                os.path.join(image_cache_dir, f"page-{page_num}.png"),
            ]
            for c in candidates:
                if os.path.exists(c):
                    img = Image.open(c)
                    break

        # ── 2. Render fresh if no cache ───────────────────────────────────
        if img is None:
            from pdf2image import convert_from_path
            images = convert_from_path(
                file_path,
                dpi=dpi,
                first_page=page_index + 1,
                last_page=page_index + 1,
                fmt="jpeg",
            )
            if not images:
                return ""
            img = images[0]

        # ── 3. OCR ────────────────────────────────────────────────────────
        text = pytesseract.image_to_string(
            img,
            lang="eng",
            config="--psm 6 --oem 3",   # uniform text block, LSTM engine
        )
        return text.strip()

    except Exception:
        return ""
