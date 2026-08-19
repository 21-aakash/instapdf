import io
import re
import logging
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

logger = logging.getLogger(__name__)

# Initialize RapidOCR engine once (lightweight ONNX runtime)
_ocr_engine = None

def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
        except Exception as e:
            logger.warning(f"Could not load RapidOCR: {e}")
            _ocr_engine = False
    return _ocr_engine if _ocr_engine is not False else None


def extract_text_from_image(image_bytes: bytes) -> str:
    """
    Extracts high-accuracy text and structure from a slide image using
    lightweight ONNX-powered RapidOCR with optimized image downscaling.
    """
    # Downscale for ultra-fast ONNX OCR inference without loss of text legibility
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if max(img.size) > 800:
            img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            ocr_bytes = buf.getvalue()
        else:
            ocr_bytes = image_bytes
    except Exception:
        ocr_bytes = image_bytes

    # 1. Primary: RapidOCR (Fast, cross-platform, pure ONNX, highly accurate on slides)
    engine = get_ocr_engine()
    if engine:
        try:
            result, _ = engine(ocr_bytes)
            if result:
                lines = [item[1].strip() for item in result if item and len(item) > 1 and item[1].strip()]
                if lines:
                    return "\n".join(lines)
        except Exception as e:
            logger.info(f"RapidOCR extraction error: {e}")

    # 2. Secondary Fallback: Microsoft MarkItDown
    try:
        from markitdown import MarkItDown
        import tempfile
        md = MarkItDown()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            tf.write(image_bytes)
            tf_path = tf.name

        res = md.convert(tf_path)
        if res and res.text_content and res.text_content.strip():
            return res.text_content.strip()
    except Exception:
        pass

    return ""


def format_slide_text_as_markdown(raw_text: str, slide_num: int) -> str:
    """
    Smart heuristic formatter: turns raw slide lines into clean Markdown
    with headings, bullet points, and code formatting where applicable.
    """
    if not raw_text or not raw_text.strip():
        return f"*Slide {slide_num} visual diagram / card.*"

    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    if not lines:
        return f"*Slide {slide_num} visual card.*"

    formatted = []
    first = lines[0]
    if len(first) < 65 and not first.startswith(("-", "*", "•", "1.", "2.")):
        formatted.append(f"### {first}")
        body_lines = lines[1:]
    else:
        body_lines = lines

    for line in body_lines:
        if line.startswith(("•", "·", "▪", "▫", "-")):
            clean = re.sub(r"^[•·▪▫-]\s*", "", line)
            formatted.append(f"- {clean}")
        elif re.match(r"^\d+[\.\)]\s+", line):
            formatted.append(line)
        else:
            formatted.append(line)

    return "\n\n".join(formatted)


def convert_slides_to_markdown(
    images_bytes: List[bytes], 
    shortcode: str, 
    caption: str = ""
) -> str:
    """
    Converts all slides of an Instagram knowledge carousel into a clean, 
    structured Markdown document using concurrent OCR processing.
    """
    doc = [
        f"# 📚 Knowledge Notes: Instagram Carousel ({shortcode})",
        "",
        f"> **Original Source:** https://www.instagram.com/p/{shortcode}/  ",
        f"> **Total Slides Extracted:** {len(images_bytes)}",
        ""
    ]

    if caption:
        doc.extend([
            "### 📌 Post Caption",
            f"> {caption.strip()}",
            "",
            "---",
            ""
        ])

    # Run OCR across slides concurrently using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(len(images_bytes), 4)) as executor:
        slide_texts = list(executor.map(extract_text_from_image, images_bytes))

    for idx, raw_text in enumerate(slide_texts, 1):
        doc.append(f"## 📄 Slide {idx}")
        doc.append("")

        formatted_md = format_slide_text_as_markdown(raw_text, idx)
        doc.append(formatted_md)

        doc.append("")
        doc.append("---")
        doc.append("")

    doc.append("*Generated automatically via InstaPDF Knowledge Engine.*")
    return "\n".join(doc)
