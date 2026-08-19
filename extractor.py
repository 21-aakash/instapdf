import io
import re
import json
import logging
from typing import List, Dict, Any, Optional
from curl_cffi import requests as curl_requests
from PIL import Image

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
]

def parse_shortcode(url: str) -> str:
    """Extracts shortcode from any Instagram URL format (posts, reels, share links, query parameters)."""
    clean_url = url.strip()
    # Match /p/SHORTCODE, /reel/SHORTCODE, /reels/SHORTCODE, /share/p/SHORTCODE
    match = re.search(r"/(?:p|reel|reels|share/p)/([A-Za-z0-9_-]+)", clean_url)
    if match:
        return match.group(1)
    
    # Check if raw shortcode was passed
    if re.match(r"^[A-Za-z0-9_-]{9,15}$", clean_url):
        return clean_url
        
    raise ValueError(f"Invalid Instagram post URL: {url}")


def _extract_via_embed(shortcode: str) -> List[str]:
    """Strategy 1: Scrape Instagram embed page (High success rate without login)."""
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    headers = {
        "User-Agent": USER_AGENTS[0],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.instagram.com/",
        "Sec-Fetch-Dest": "iframe",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
    }
    
    resp = curl_requests.get(embed_url, headers=headers, impersonate="chrome", timeout=20)
    resp.raise_for_status()
    html = resp.text

    img_urls: List[str] = []
    seen: set = set()

    # Match display_url from JS payload
    raw_matches = re.findall(r'"display_url"\s*:\s*"([^"]+)"', html)
    for u in raw_matches:
        decoded = u.replace("\\u0026", "&").replace("\\/", "/")
        if decoded not in seen:
            seen.add(decoded)
            img_urls.append(decoded)

    # Match JSON-LD or embedded media array
    if not img_urls:
        media_matches = re.findall(r'"images"\s*:\s*\[(.*?)\]', html, re.DOTALL)
        for block in media_matches:
            urls = re.findall(r'"url"\s*:\s*"([^"]+)"', block)
            for u in urls:
                decoded = u.replace("\\u0026", "&").replace("\\/", "/")
                if decoded not in seen:
                    seen.add(decoded)
                    img_urls.append(decoded)

    # Match Embedded image tags
    if not img_urls:
        embedded_imgs = re.findall(r'<img[^>]+class="EmbeddedMediaImage"[^>]+src="([^"]+)"', html)
        for u in embedded_imgs:
            decoded = u.replace("&amp;", "&")
            if decoded not in seen:
                seen.add(decoded)
                img_urls.append(decoded)

    return img_urls


def _extract_via_json_api(shortcode: str, session_id: str = "") -> List[str]:
    """Strategy 2: Query Instagram ?__a=1&__d=dis JSON endpoint."""
    api_url = f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis"
    headers = {
        "User-Agent": USER_AGENTS[0],
        "X-IG-App-ID": "936619743392459",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://www.instagram.com/p/{shortcode}/",
        "Accept": "*/*"
    }
    if session_id:
        headers["Cookie"] = f"sessionid={session_id};"

    resp = curl_requests.get(api_url, headers=headers, impersonate="chrome", timeout=20)
    if resp.status_code != 200:
        return []

    try:
        data = resp.json()
    except Exception:
        return []

    items = data.get("items", [])
    if not items:
        graphql = data.get("graphql", {}).get("shortcode_media", {})
        if graphql:
            # GraphSidecar (Carousel)
            edges = graphql.get("edge_sidecar_to_children", {}).get("edges", [])
            if edges:
                return [edge["node"]["display_url"] for edge in edges if "node" in edge]
            if "display_url" in graphql:
                return [graphql["display_url"]]
        return []

    post_data = items[0]
    # Carousel items
    carousel_media = post_data.get("carousel_media", [])
    if carousel_media:
        urls = []
        for media in carousel_media:
            candidates = media.get("image_versions2", {}).get("candidates", [])
            if candidates:
                # Highest resolution candidate
                urls.append(candidates[0]["url"])
        if urls:
            return urls

    # Single Image
    single_candidates = post_data.get("image_versions2", {}).get("candidates", [])
    if single_candidates:
        return [single_candidates[0]["url"]]

    return []


def _extract_via_instaloader(shortcode: str, session_id: str = "") -> List[str]:
    """Strategy 3: Instaloader SDK fallback."""
    try:
        import instaloader
        L = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            save_metadata=False,
            compress_json=False,
            quiet=True
        )
        if session_id:
            L.context._session.cookies.update({"sessionid": session_id})

        post = instaloader.Post.from_shortcode(L.context, shortcode)
        img_urls: List[str] = []
        if post.typename == "GraphSidecar":
            for node in post.get_sidecar_nodes():
                if not node.is_video:
                    img_urls.append(node.display_url)
        elif not post.is_video:
            img_urls.append(post.url)
        return img_urls
    except Exception as e:
        logger.warning(f"Instaloader strategy failed: {e}")
        return []


def extract_carousel_images(shortcode: str, session_id: str = "") -> Dict[str, Any]:
    """
    Multi-stage resilient extraction hierarchy for Instagram carousel and post images.
    Tries Embed scraper -> JSON API -> Instaloader.
    """
    urls: List[str] = []

    # 1. Embed Scraper
    try:
        urls = _extract_via_embed(shortcode)
    except Exception as e:
        logger.info(f"Embed extraction failed for {shortcode}: {e}")

    # 2. JSON API
    if not urls:
        try:
            urls = _extract_via_json_api(shortcode, session_id)
        except Exception as e:
            logger.info(f"JSON API extraction failed for {shortcode}: {e}")

    # 3. Instaloader Fallback
    if not urls:
        urls = _extract_via_instaloader(shortcode, session_id)

    if not urls:
        if session_id:
            raise ValueError("Could not extract slides. The post might be private or the provided sessionid cookie is expired.")
        raise ValueError("Instagram blocked the public request. Please verify the post is public or provide your sessionid cookie in Advanced Settings.")

    return {
        "shortcode": shortcode,
        "slide_count": len(urls),
        "slides": [{"index": i + 1, "url": u} for i, u in enumerate(urls)]
    }


def fetch_image_bytes(url: str) -> bytes:
    """Download image with Chrome TLS fingerprint impersonation."""
    headers = {
        "User-Agent": USER_AGENTS[0],
        "Referer": "https://www.instagram.com/",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
    }
    resp = curl_requests.get(url, headers=headers, impersonate="chrome", timeout=30)
    resp.raise_for_status()
    return resp.content


def convert_images_to_pdf(images_bytes: List[bytes]) -> bytes:
    """Convert high-res images to multi-page PDF with auto-orientation and DPI normalization."""
    try:
        import img2pdf
        return img2pdf.convert(images_bytes)
    except Exception:
        pass

    # Fallback to Pillow
    pil_pages = []
    for raw in images_bytes:
        img = Image.open(io.BytesIO(raw))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        pil_pages.append(img)

    if not pil_pages:
        raise ValueError("No valid image frames to compile into PDF.")

    buf = io.BytesIO()
    pil_pages[0].save(
        buf,
        format="PDF",
        save_all=True,
        append_images=pil_pages[1:],
        resolution=100.0,
        quality=95
    )
    return buf.getvalue()
