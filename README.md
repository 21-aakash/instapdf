# 📸 InstaPDF - Instagram Carousel to PDF & Image Tool

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](Dockerfile)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An async **FastAPI web application** that extracts all slides from public Instagram carousels, posts, and reels and compiles them into a single high-resolution PDF or ZIP package.

---

## ⚡ Key Improvements & Architecture

* **FastAPI Async Engine:** Migrated from Flask to FastAPI for non-blocking stream downloads (`StreamingResponse`) and sub-second slide previews.
* **Multi-Stage Resilient Extractor (`extractor.py`):**
  1. **Public Embed Scraper:** Scrapes `/p/{shortcode}/embed/captioned/` with Chrome TLS fingerprinting to bypass login walls.
  2. **JSON API Fallback:** Queries `?__a=1&__d=dis` with mobile App-ID headers.
  3. **Instaloader SDK:** Robust fallback with optional session cookie support for rate-limited profiles.
* **Universal URL Support:** Supports posts (`/p/`), reels (`/reel/`), share links (`/share/p/`), and URLs with query parameters (`?img_index=...`).
* **High-DPI PDF Generation:** Lossless vector-level PDF conversion via `img2pdf` with automated orientation and DPI normalization.
* **Interactive Web Interface:** Real-time slide thumbnail preview on link paste, single-click PDF/ZIP download, and dark glassmorphic styling.

---

## 🚀 Quickstart

### 1. Local Run
```bash
cd d-insta_app
pip install -r requirements.txt
python app.py
```
*The browser will automatically open to `http://localhost:7860`.*

---

## 🐳 Docker Run

```bash
docker-compose up -d --build
```
Access at `http://localhost:7860`.

---

## ☁️ 1-Click Deploy Options

### A. Deploy to Render
1. Push this repository to GitHub.
2. Link your GitHub repo to [Render.com](https://render.com).
3. Render will auto-detect `render.yaml` and deploy the web service on the free tier.

### B. Deploy to Hugging Face Spaces
```bash
python deploy.py --space your-username/instapdf-space
```

### C. Deploy to Railway / Fly.io / GCP Cloud Run
Simply point your deployment target to the included `Dockerfile` (Port: `7860` or `$PORT`).
