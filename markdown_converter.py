import io
import re
import tempfile
from typing import List, Optional
from PIL import Image

def extract_text_from_image(image_bytes: bytes) -> str:
    """Extracts text from a single slide image using MarkItDown or OCR fallback."""
    # 1. Try MarkItDown
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            tf.write(image_bytes)
            tf_path = tf.name

        result = md.convert(tf_path)
        if result and result.text_content and result.text_content.strip():
            return result.text_content.strip()
    except Exception:
        pass

    # 2. Try pytesseract if installed and configured
    try:
        import pytesseract
        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img)
        if text and text.strip():
            return text.strip()
    except Exception:
        pass

    return ""


def convert_slides_to_markdown(
    images_bytes: List[bytes], 
    shortcode: str, 
    caption: str = ""
) -> str:
    """
    Converts all slides of an Instagram knowledge carousel into a clean, 
    structured Markdown document.
    """
    lines = [
        f"# 📚 Knowledge Notes: Instagram Carousel ({shortcode})",
        "",
        f"> **Source URL:** https://www.instagram.com/p/{shortcode}/  ",
        f"> **Total Slides:** {len(images_bytes)}",
        ""
    ]

    if caption:
        lines.extend([
            "### 📌 Post Caption",
            f"> {caption.strip()}",
            "",
            "---",
            ""
        ])

    for idx, raw in enumerate(images_bytes, 1):
        lines.append(f"## 📄 Slide {idx}")
        lines.append("")

        text = extract_text_from_image(raw)
        if text:
            # Clean excessive newlines
            clean_text = re.sub(r"\n{3,}", "\n\n", text)
            lines.append(clean_text)
        else:
            lines.append(f"*Slide {idx} captured in high resolution (diagram/visual card).*")

        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("*Generated automatically via InstaPDF Knowledge Engine.*")
    return "\n".join(lines)
