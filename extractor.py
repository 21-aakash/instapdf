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
    match = re.search(r"/(?:p|reel|reels|share/p)/([A-Za-z0-9_-]+)", clean_url)
    if match:
        return match.group(1)
    
    if re.match(r"^[A-Za-z0-9_-]{9,15}$", clean_url):
        return clean_url
        
    raise ValueError(f"Invalid Instagram post URL: {url}")


def _extract_via_instaloader(shortcode: str, session_id: str = "") -> List[str]:
    """Primary Strategy: Instaloader SDK — fully parses GraphSidecar carousels and returns all slides."""
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
                # Prefer high-res image
                if not node.is_video:
                    img_urls.append(node.display_url)
                elif hasattr(node, "display_url") and node.display_url:
                    img_urls.append(node.display_url)
        elif not post.is_video:
            img_urls.append(post.url)
        elif hasattr(post, "url") and post.url:
            img_urls.append(post.url)

        if img_urls:
            return img_urls
    except Exception as e:
        logger.warning(f"Instaloader strategy failed for {shortcode}: {e}")
        
    return []


def _extract_via_json_api(shortcode: str, session_id: str = "") -> List[str]:
    """Secondary Strategy: Instagram internal API with X-IG-App-ID headers."""
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

    try:
        resp = curl_requests.get(api_url, headers=headers, impersonate="chrome", timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            if items:
                post_data = items[0]
                carousel_media = post_data.get("carousel_media", [])
                if carousel_media:
                    urls = []
                    for media in carousel_media:
                        candidates = media.get("image_versions2", {}).get("candidates", [])
                        if candidates:
                            urls.append(candidates[0]["url"])
                    if urls:
                        return urls

                single_candidates = post_data.get("image_versions2", {}).get("candidates", [])
                if single_candidates:
                    return [single_candidates[0]["url"]]

            graphql = data.get("graphql", {}).get("shortcode_media", {})
            if graphql:
                edges = graphql.get("edge_sidecar_to_children", {}).get("edges", [])
                if edges:
                    return [edge["node"]["display_url"] for edge in edges if "node" in edge]
                if "display_url" in graphql:
                    return [graphql["display_url"]]
    except Exception as e:
        logger.info(f"JSON API strategy error: {e}")

    return []


def _extract_via_embed(shortcode: str) -> List[str]:
    """Tertiary Strategy: Scrape Instagram embed page (Works for single image posts as fallback)."""
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    headers = {
        "User-Agent": USER_AGENTS[0],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://www.instagram.com/",
    }
    
    try:
        resp = curl_requests.get(embed_url, headers=headers, impersonate="chrome", timeout=20)
        if resp.status_code == 200:
            html = resp.text
            raw_matches = re.findall(r'"display_url"\s*:\s*"([^"]+)"', html)
            seen = set()
            img_urls = []
            for u in raw_matches:
                decoded = u.replace("\\u0026", "&").replace("\\/", "/")
                if decoded not in seen:
                    seen.add(decoded)
                    img_urls.append(decoded)
            if img_urls:
                return img_urls
    except Exception as e:
        logger.info(f"Embed extraction fallback error: {e}")

    return []


def extract_carousel_images(shortcode: str, session_id: str = "") -> Dict[str, Any]:
    """
    Multi-stage resilient extraction hierarchy for Instagram carousels and posts.
    Prioritizes full sidecar node extraction across all carousel slides.
    """
    # 1. Try Instaloader (Full GraphSidecar extraction)
    urls = _extract_via_instaloader(shortcode, session_id)

    # 2. Try JSON API
    if not urls:
        urls = _extract_via_json_api(shortcode, session_id)

    # 3. Try Embed fallback
    if not urls:
        urls = _extract_via_embed(shortcode)

    if not urls:
        if session_id:
            raise ValueError("Could not extract slides. The post might be private or the provided sessionid cookie is expired.")
        raise ValueError("Instagram blocked the request. Please verify the post is public or provide your sessionid cookie in Advanced Settings.")

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
