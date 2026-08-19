# 📸 InstaPDF & Knowledge Markdown Engine

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Multi--Stage-2496ED?style=for-the-badge&logo=docker&logoColor=white)](Dockerfile)
[![Render](https://img.shields.io/badge/Render-Live%20Deploy-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://instapdf.onrender.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

An asynchronous, production-grade **FastAPI microservice and web application** designed to liberate educational slide decks, infographics, and tutorials from public Instagram carousels into **lossless multi-page PDFs**, **structured Markdown (`.md`) notes**, and **high-resolution image packages**.

🌐 **Live Web App:** [https://instapdf.onrender.com](https://instapdf.onrender.com)  
📖 **Interactive Swagger Docs:** [https://instapdf.onrender.com/docs](https://instapdf.onrender.com/docs)

---

## ⚡ Problem Statement & Why This Exists

Technical educators, engineers, and creators frequently share high-value programming guides, system architecture diagrams, and cheat sheets on Instagram. However, Instagram treats these as ephemeral images locked within a closed app with no native export option.

**InstaPDF solves this by providing:**
1. **Lossless Document Preservation:** Compiles all carousel slides into an ordered, high-DPI, multi-page PDF for offline reading and archiving.
2. **Knowledge Extraction for PKM Tools:** Converts visual slides into structured GitHub-Flavored Markdown (`.md`) via **Microsoft MarkItDown** for immediate import into **Obsidian**, **Notion**, or **Logseq**.
3. **Developer-Friendly API:** Async REST endpoints to programmatically ingest carousel content into RAG knowledge bases.

---

## 🌟 Core Capabilities

* **📑 Lossless Vector-Level PDF Compilation:** Direct binary image embedding using `img2pdf`, preserving exact pixel ratios, orientation, and DPI without lossy re-compression.
* **📝 MarkItDown Knowledge Notes Engine:** Integrates Microsoft's `markitdown` and optical analysis to extract text, code blocks, lists, and headings into ready-to-use `.md` files.
* **📦 Raw Asset Packaging:** Generates structured `.zip` archives of original high-resolution JPEGs.
* **📱 Mobile-First Interactive Web App:** 
  * 1-tap clipboard paste button (`📋 Paste`).
  * Real-time slide thumbnail preview on link input.
  * Swipeable horizontal slide deck with tap-to-zoom fullscreen lightbox.
  * Live 3-step progress bar (`1/3: Extracting nodes` $\rightarrow$ `2/3: Fetching frames` $\rightarrow$ `3/3: Compiling document`).
  * Instant Light ☀️ / Dark 🌙 theme toggle with persistent memory.
* **🛡️ Built-in Rate Limiting & Protection:** Backed by **SlowAPI** sliding-window throttling and reverse-proxy IP detection.
* **⚡ 15-Minute TTL Memory Cache:** Prevents duplicate network requests to Instagram CDN when previewing and downloading the same carousel.

---

## 🏗️ Deep Architectural Technicalities

```
                         ┌─────────────────────────────────┐
                         │   Client (Web UI / REST API)   │
                         └────────────────┬────────────────┘
                                          │
                                 [ SlowAPI Limiter ]
                                 [ 40 req/m Preview]
                                 [ 20 req/m Download]
                                          │
                                   [ TTLCache ]
                           (15-min Memory Cache hit?)
                                 /                \
                             [YES]                [NO]
                              /                      \
                    Return Cached Nodes        [ Extractor Hierarchy ]
                                              1. Instaloader (GraphSidecar)
                                              2. Internal JSON API (App-ID)
                                              3. Public Embed Scraper (curl-cffi)
                                                      │
                                           [ In-Memory Byte Stream ]
                                          /           |           \
                                         /            |            \
                                  [img2pdf]     [MarkItDown]    [zipfile]
                                     ↓               ↓              ↓
                                 Multi-Page      Structured      High-Res
                                    PDF           Markdown         ZIP
```

### 1. Resilient Multi-Stage Extraction (`extractor.py`)
Instagram restricts automated scraping through aggressive login walls and IP blocks. InstaPDF employs a hierarchical traversal pipeline:
1. **Primary (`GraphSidecar` Node Traversal):** Leverages Instaloader's context engine to traverse all child nodes (`post.get_sidecar_nodes()`), guaranteeing that all 10 slides of a carousel are discovered rather than just the cover thumbnail.
2. **Secondary (Internal Mobile JSON API):** Issues authenticated headers with Instagram's mobile `X-IG-App-ID: 936619743392459` to retrieve the `carousel_media` candidate array.
3. **Tertiary (Public Embed Scraper):** Scrapes `/p/{shortcode}/embed/captioned/` utilizing `curl_cffi` Chrome TLS fingerprint impersonation to defeat basic bot-blocking heuristics.

### 2. Microsoft MarkItDown Knowledge Conversion (`markdown_converter.py`)
Transforms visual slide frames into structured Markdown notes:
* Extracts text, headers, and bulleted takeaways.
* Generates source metadata headers (URL, slide count, timestamp).
* Outputs clean GitHub Flavored Markdown (`.md`) formatted for personal knowledge bases.

### 3. Rate Limiting & Memory Caching (`cache_and_limiter.py`)
* **SlowAPI Throttling:** Strict per-IP rate limiting (`40/min` for previews, `20/min` for downloads) to prevent resource exhaustion and denial of service.
* **TTLCache:** Thread-safe, in-memory cache retaining extracted slide nodes for 15 minutes. Eliminates 80%+ of outbound network requests during typical preview $\rightarrow$ download workflows.

---

## 📡 REST API Reference

### 1. Preview Carousel Metadata
```http
POST /api/preview
Content-Type: application/json
```
**Request:**
```json
{
  "url": "https://www.instagram.com/p/DcLBRA0E14z/",
  "session_id": ""
}
```
**Response:**
```json
{
  "success": true,
  "shortcode": "DcLBRA0E14z",
  "slide_count": 7,
  "slides": [
    { "index": 1, "url": "https://scontent...jpg" },
    { "index": 2, "url": "https://scontent...jpg" }
  ],
  "cached": false
}
```

---

### 2. Download Document / Archive
```http
POST /api/download
Content-Type: application/json
```
**Request:**
```json
{
  "url": "https://www.instagram.com/p/DcLBRA0E14z/",
  "format": "pdf", // Options: "pdf" | "md" | "zip"
  "session_id": ""
}
```
**Response:** Streams binary attachment (`application/pdf`, `text/markdown`, or `application/zip`).

---

## 🚀 Local Setup & Development

### Prerequisites
* Python 3.11+
* Git

```bash
# 1. Clone the repository
git clone https://github.com/21-aakash/instapdf.git
cd instapdf

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start development server
python app.py
```
*App will launch at `http://localhost:7860`.*

---

## 🐳 Docker Deployment

### Multi-Stage Build
The included [`Dockerfile`](Dockerfile) uses a 2-stage build with an unprivileged `appuser` for optimal security and minimal image size:

```bash
# Build & run container
docker build -t instapdf:latest .
docker run -d -p 7860:7860 --name instapdf instapdf:latest
```

### Docker Compose
```bash
docker-compose up -d --build
```
Access at `http://localhost:7860`.

---

## ☁️ 1-Click Cloud Deployment

### A. Deploy to Render (Free Tier)
1. Fork / push this repo to your GitHub account.
2. Create a new **Web Service** on [Render](https://render.com) and select this repository.
3. Render automatically detects [`render.yaml`](render.yaml) and configures the service.

### B. Deploy to Hugging Face Spaces
```bash
pip install huggingface-hub
python deploy.py --space your-username/instapdf
```

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.
