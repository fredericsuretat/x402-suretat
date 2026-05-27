from __future__ import annotations
import logging
import os
import re
import time
from urllib.parse import urljoin, urlparse

import httpx
import uvicorn
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-urlmeta")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; x402-urlmeta/1.0; +https://x402-urlmeta.suretat.com)",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "fr,en;q=0.9",
}

app = FastAPI(title="x402 URL Metadata Extractor", version="1.0.0")


class URLRequest(BaseModel):
    url: str = Field(..., description="URL à analyser", examples=["https://example.com"])
    follow_redirects: bool = Field(default=True)
    timeout: int = Field(default=10, ge=1, le=30)


def extract_meta(html: str, base_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    def og(prop):
        tag = soup.find("meta", property=f"og:{prop}") or soup.find("meta", attrs={"name": f"og:{prop}"})
        return tag.get("content", "").strip() if tag else None

    def tw(name):
        tag = soup.find("meta", attrs={"name": f"twitter:{name}"})
        return tag.get("content", "").strip() if tag else None

    def meta(name):
        tag = soup.find("meta", attrs={"name": name})
        return tag.get("content", "").strip() if tag else None

    title = (
        og("title") or
        tw("title") or
        (soup.title.get_text(strip=True) if soup.title else None) or
        None
    )

    description = (
        og("description") or
        tw("description") or
        meta("description") or
        None
    )

    image = og("image") or tw("image")
    if image and not image.startswith("http"):
        image = urljoin(base_url, image)

    favicon = None
    for rel in ["icon", "shortcut icon", "apple-touch-icon"]:
        link = soup.find("link", rel=lambda r, _rel=rel: r and _rel in (r if isinstance(r, list) else [r]))
        if link and link.get("href"):
            favicon = urljoin(base_url, link["href"])
            break
    if not favicon:
        parsed = urlparse(base_url)
        favicon = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"

    canonical = None
    canon_tag = soup.find("link", rel="canonical")
    if canon_tag:
        canonical = canon_tag.get("href")

    robots = meta("robots")
    keywords = meta("keywords")
    author = meta("author") or og("site_name")
    locale = og("locale") or meta("language")
    site_name = og("site_name")
    og_type = og("type")

    # Extract all links count
    links = soup.find_all("a", href=True)
    internal = sum(1 for l in links if not l["href"].startswith("http"))
    external = sum(1 for l in links if l["href"].startswith("http"))

    # Structured data (JSON-LD)
    schema_types = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                t = data.get("@type")
                if t:
                    schema_types.append(t)
        except Exception:
            pass

    return {
        "titre": title,
        "description": description,
        "image_og": image,
        "favicon": favicon,
        "canonical": canonical,
        "site_name": site_name,
        "og_type": og_type,
        "locale": locale,
        "auteur": author,
        "mots_cles": keywords,
        "robots": robots,
        "liens_internes": internal,
        "liens_externes": external,
        "schema_types": schema_types,
        "twitter_card": tw("card"),
    }


@app.get("/")
def root():
    return {
        "service": "x402 URL Metadata Extractor",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.001 USDC/URL",
        "endpoint": "POST /extract",
        "extraits": ["titre", "description", "og:image", "favicon", "canonical", "schema.org", "twitter card"],
        "docs": "/docs",
        "tagline": "Extract metadata from any URL — title, description, og:image, HTTP headers",
        "curl_example": "curl https://x402-urlmeta.suretat.com/meta -H 'Content-Type: application/json' -d '{\"url\": \"https://github.com\"}'",
        "try_it": "https://x402-urlmeta.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/extract" and request.method == "POST":
        auth = request.headers.get("X-PAYMENT") or request.headers.get("x-payment")
        if not auth:
            return JSONResponse(
                status_code=402,
                content={
                    "x402Version": 1,
                    "error": "Payment required",
                    "accepts": [{
                        "scheme": "exact",
                        "network": NETWORK,
                        "maxAmountRequired": PRICE_ATOMIC,
                        "resource": "https://" + request.headers.get("host", str(request.url.hostname)) + str(request.url.path),
                        "description": "URL Metadata extraction — 0.001 USDC",
                        "mimeType": "application/json",
                        "payTo": PAY_TO,
                        "maxTimeoutSeconds": 300,
                        "asset": ASSET_ADDRESS,
                        "extra": {"name": "USDC", "version": "2"},
                    }],
                },
                headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
            )
    return await call_next(request)


@app.post("/extract")
async def extract(req: URLRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=req.follow_redirects,
            timeout=req.timeout,
        ) as client:
            resp = await client.get(req.url)
            final_url = str(resp.url)
            status_code = resp.status_code
            content_type = resp.headers.get("content-type", "")

        if "text/html" not in content_type:
            return {
                "url": req.url,
                "url_finale": final_url,
                "status_http": status_code,
                "content_type": content_type,
                "erreur": "La ressource n'est pas une page HTML",
            }

        meta = extract_meta(resp.text, final_url)
        return {
            "url": req.url,
            "url_finale": final_url,
            "status_http": status_code,
            "content_type": content_type,
            **meta,
        }

    except httpx.TimeoutException:
        return JSONResponse(status_code=408, content={"error": f"Timeout après {req.timeout}s", "url": req.url})
    except httpx.RequestError as e:
        return JSONResponse(status_code=400, content={"error": f"Erreur réseau: {str(e)}", "url": req.url})



@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK if "NETWORK" in dir() else os.getenv("NETWORK", "base"),
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/extract",
            "description": "x402 URL Metadata Extractor",
            "mimeType": "application/json",
            "payTo": PAY_TO if "PAY_TO" in dir() else os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b"),
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS if "ASSET_ADDRESS" in dir() else "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "extra": {"name": "USDC", "version": "2"},
        }]
    }

@app.get("/.well-known/x402")
async def x402_well_known_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/.well-known/x402.json")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3047)
