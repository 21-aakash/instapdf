#!/usr/bin/env python3
"""
Instagram Carousel to PDF / Markdown / Image Downloader (FastAPI)
Features:
- Multi-stage resilient extraction (GraphSidecar child nodes)
- High-DPI lossless PDF generation
- Microsoft MarkItDown & OCR knowledge extraction
- SlowAPI client IP rate limiting
- In-memory TTL response caching
- Production Docker & Cloud readiness
"""

import io
import os
import zipfile
import webbrowser
from threading import Timer
from typing import Optional, List, Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from extractor import (
    parse_shortcode,
    extract_carousel_images,
    fetch_image_bytes,
    convert_images_to_pdf
)
from markdown_converter import convert_slides_to_markdown
from cache_and_limiter import TTLCache

PORT = int(os.environ.get("PORT", 7860))

# SlowAPI Rate Limiter instance
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

app = FastAPI(
    title="InstaPDF & Knowledge Markdown Engine",
    version="2.3.0",
    description="High-performance async tool to convert Instagram carousels into high-DPI PDFs, clean Markdown notes, or image packages."
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

# In-memory metadata & slide extraction cache (15 min TTL)
metadata_cache = TTLCache(ttl_seconds=900, max_entries=200)


class PreviewRequest(BaseModel):
    url: str = Field(..., description="Instagram post or reel URL")
    session_id: Optional[str] = Field(default="", description="Optional Instagram sessionid cookie")


class DownloadRequest(BaseModel):
    url: str
    format: Literal["pdf", "md", "zip"] = "pdf"
    session_id: Optional[str] = ""


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def index_view(request: Request):
    return templates.TemplateResponse(name="index.html", request=request)


@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    return {
        "status": "healthy",
        "service": "insta-carousel-to-pdf-and-markdown",
        "version": "2.3.0",
        "rate_limiting": "SlowAPI enabled"
    }


@app.post("/api/preview")
@limiter.limit("40/minute")
async def preview_carousel(request: Request, req: PreviewRequest):
    """Parses URL, runs cached multi-stage extraction, and returns slide thumbnails."""
    try:
        shortcode = parse_shortcode(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check cache first
    cached_data = metadata_cache.get(f"{shortcode}:{req.session_id or ''}")
    if cached_data:
        return {
            "success": True,
            "shortcode": cached_data["shortcode"],
            "slide_count": cached_data["slide_count"],
            "slides": cached_data["slides"],
            "cached": True
        }

    try:
        data = extract_carousel_images(shortcode, req.session_id or "")
        metadata_cache.set(f"{shortcode}:{req.session_id or ''}", data)
        return {
            "success": True,
            "shortcode": data["shortcode"],
            "slide_count": data["slide_count"],
            "slides": data["slides"],
            "cached": False
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/download")
@limiter.limit("20/minute")
async def download_carousel(request: Request, req: DownloadRequest):
    """Downloads all high-res slides and returns compiled PDF, Markdown (.md), or ZIP archive."""
    try:
        shortcode = parse_shortcode(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Leverage cache if previously previewed
    cached_data = metadata_cache.get(f"{shortcode}:{req.session_id or ''}")
    if cached_data:
        data = cached_data
    else:
        try:
            data = extract_carousel_images(shortcode, req.session_id or "")
            metadata_cache.set(f"{shortcode}:{req.session_id or ''}", data)
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    slides = data.get("slides", [])
    if not slides:
        raise HTTPException(status_code=404, detail="No downloadable images found in this post.")

    # Fetch all slides into memory
    images_bytes: List[bytes] = []
    for item in slides:
        try:
            b = fetch_image_bytes(item["url"])
            images_bytes.append(b)
        except Exception:
            continue

    if not images_bytes:
        raise HTTPException(status_code=502, detail="Failed to fetch image frames from CDN.")

    # Format 1: Single Multi-Page PDF
    if req.format == "pdf":
        try:
            pdf_data = convert_images_to_pdf(images_bytes)
            return StreamingResponse(
                io.BytesIO(pdf_data),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="insta_{shortcode}.pdf"',
                    "X-Total-Slides": str(len(images_bytes))
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF generation error: {e}")

    # Format 2: Markdown Knowledge Document
    elif req.format == "md":
        try:
            md_content = convert_slides_to_markdown(images_bytes, shortcode)
            return StreamingResponse(
                io.BytesIO(md_content.encode("utf-8")),
                media_type="text/markdown; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="insta_{shortcode}_notes.md"',
                    "X-Total-Slides": str(len(images_bytes))
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Markdown conversion error: {e}")

    # Format 3: ZIP Package of high-res JPEGs
    else:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for idx, raw in enumerate(images_bytes, 1):
                zf.writestr(f"slide_{idx:02d}.jpg", raw)
        zip_buf.seek(0)
        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="insta_{shortcode}_slides.zip"',
                "X-Total-Slides": str(len(images_bytes))
            }
        )


if __name__ == "__main__":
    import uvicorn
    Timer(1.2, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)
