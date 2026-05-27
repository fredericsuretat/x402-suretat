from __future__ import annotations
import logging
import os
import time
from datetime import datetime

import feedparser
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-rss")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; x402-rss/1.0; +https://x402-rss.suretat.com)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.8",
}

app = FastAPI(title="x402 RSS Feed Parser", version="1.0.0")


class RSSRequest(BaseModel):
    url: str = Field(..., description="URL du flux RSS ou Atom")
    limit: int = Field(default=10, ge=1, le=50, description="Nombre maximum d'articles")
    include_content: bool = Field(default=False, description="Inclure le contenu complet des articles")


def _entry_to_dict(entry, include_content: bool) -> dict:
    published = None
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            published = datetime(*entry.published_parsed[:6]).isoformat()
        except Exception:
            pass
    if not published and hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            published = datetime(*entry.updated_parsed[:6]).isoformat()
        except Exception:
            pass

    result = {
        "titre": entry.get("title", "").strip(),
        "lien": entry.get("link", ""),
        "auteur": entry.get("author", None),
        "publie_le": published,
        "resume": (entry.get("summary", "") or "")[:500].strip() or None,
        "categories": [t.term for t in entry.get("tags", [])] if entry.get("tags") else [],
    }

    if include_content:
        content = ""
        if hasattr(entry, "content") and entry.content:
            content = entry.content[0].get("value", "")
        elif entry.get("summary"):
            content = entry.get("summary", "")
        result["contenu_html"] = content[:10000] if content else None

    return result


@app.get("/")
def root():
    return {
        "service": "x402 RSS Feed Parser",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.001 USDC/flux",
        "endpoint": "POST /parse",
        "formats": ["RSS 0.90", "RSS 1.0", "RSS 2.0", "Atom 0.3", "Atom 1.0"],
        "docs": "/docs",
        "tagline": "Parse any RSS or Atom feed — returns structured JSON with articles",
        "curl_example": "curl https://x402-rss.suretat.com/parse -H 'Content-Type: application/json' -d '{\"url\": \"https://news.ycombinator.com/rss\", \"limit\": 5}'",
        "try_it": "https://x402-rss.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/parse" and request.method == "POST":
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
                        "description": "RSS Feed parsing — 0.001 USDC",
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


@app.post("/parse")
async def parse_feed(req: RSSRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(req.url)
            raw = resp.text
    except httpx.TimeoutException:
        return JSONResponse(status_code=408, content={"error": f"Timeout lors du téléchargement du flux", "url": req.url})
    except httpx.RequestError as e:
        return JSONResponse(status_code=400, content={"error": f"Erreur réseau: {e}", "url": req.url})

    feed = feedparser.parse(raw)

    if feed.bozo and not feed.entries:
        return JSONResponse(status_code=422, content={
            "error": "Flux invalide ou non parseable",
            "url": req.url,
            "detail": str(feed.bozo_exception) if hasattr(feed, "bozo_exception") else "Format inconnu",
        })

    # Feed metadata
    channel = {
        "titre": feed.feed.get("title", "").strip(),
        "description": (feed.feed.get("description", "") or feed.feed.get("subtitle", ""))[:300].strip() or None,
        "lien": feed.feed.get("link", req.url),
        "langue": feed.feed.get("language", None),
        "auteur": feed.feed.get("author", None),
        "image": feed.feed.get("image", {}).get("href") if hasattr(feed.feed.get("image", None), "get") else None,
    }

    articles = [
        _entry_to_dict(entry, req.include_content)
        for entry in feed.entries[:req.limit]
    ]

    return {
        "url": req.url,
        "format": feed.version or "inconnu",
        "nb_articles": len(feed.entries),
        "nb_retournes": len(articles),
        "canal": channel,
        "articles": articles,
    }



@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK if "NETWORK" in dir() else os.getenv("NETWORK", "base"),
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/parse",
            "description": "x402 RSS Feed Parser",
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
    uvicorn.run(app, host="0.0.0.0", port=3058)
