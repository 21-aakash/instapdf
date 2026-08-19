#!/usr/bin/env python3
"""
Instagram Carousel to PDF / Image Downloader (FastAPI)
Run: python app.py  ->  http://localhost:7860
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

from extractor import (
    parse_shortcode,
    extract_carousel_images,
    fetch_image_bytes,
    convert_images_to_pdf
)

PORT = int(os.environ.get("PORT", 7860))

app = FastAPI(
    title="Instagram Carousel to PDF API",
    version="2.0.0",
    description="High-performance async tool to convert public Instagram carousels and posts into PDFs or image packages."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")


class PreviewRequest(BaseModel):
    url: str = Field(..., description="Instagram post or reel URL")
    session_id: Optional[str] = Field(default="", description="Optional Instagram sessionid cookie")


class DownloadRequest(BaseModel):
    url: str
    format: Literal["pdf", "zip"] = "pdf"
    session_id: Optional[str] = ""


@app.get("/", response_class=HTMLResponse)
async def index_view(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "insta-carousel-to-pdf"}


@app.post("/api/preview")
async def preview_carousel(req: PreviewRequest):
    """Parses URL, runs multi-stage extraction, and returns slide thumbnails."""
    try:
        shortcode = parse_shortcode(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        data = extract_carousel_images(shortcode, req.session_id or "")
        return {
            "success": True,
            "shortcode": data["shortcode"],
            "slide_count": data["slide_count"],
            "slides": data["slides"]
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/download")
async def download_carousel(req: DownloadRequest):
    """Downloads all high-res slides and returns compiled PDF or ZIP archive."""
    try:
        shortcode = parse_shortcode(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        data = extract_carousel_images(shortcode, req.session_id or "")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    slides = data.get("slides", [])
    if not slides:
        raise HTTPException(status_code=404, detail="No downloadable images found in this post.")

    # Fetch all slides in parallel / memory
    images_bytes: List[bytes] = []
    for item in slides:
        try:
            b = fetch_image_bytes(item["url"])
            images_bytes.append(b)
        except Exception as e:
            continue

    if not images_bytes:
        raise HTTPException(status_code=502, detail="Failed to fetch image frames from CDN.")

    if req.format == "pdf":
        try:
            pdf_data = convert_images_to_pdf(images_bytes)
            return StreamingResponse(
                io.BytesIO(pdf_data),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="insta_{shortcode}.pdf"'
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF generation error: {e}")
    else:
        # ZIP Package
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for idx, raw in enumerate(images_bytes, 1):
                zf.writestr(f"slide_{idx:02d}.jpg", raw)
        zip_buf.seek(0)
        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="insta_{shortcode}_slides.zip"'
            }
        )


if __name__ == "__main__":
    import uvicorn
    # Auto-open browser tab after 1 second on local run
    Timer(1.2, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)
