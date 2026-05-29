from __future__ import annotations
import os
import re
import time
from urllib.parse import urljoin, urlparse

import httpx
import uvicorn
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; x402-social-meta/1.0; +https://x402-social-meta.suretat.com)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "fr,en;q=0.9",
}

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Social Meta Extractor", version="1.0.0")


class MetaRequest(BaseModel):
    url: str
    timeout: float = 10.0


def _extract_favicon(soup: BeautifulSoup, base_url: str) -> str | None:
    for rel in ("icon", "shortcut icon", "apple-touch-icon"):
        tag = soup.find("link", rel=rel)
        if tag and tag.get("href"):
            href = tag["href"]
            if isinstance(href, list):
                href = href[0]
            return urljoin(base_url, href)
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"


def _meta(soup: BeautifulSoup, *attrs) -> str | None:
    for attr_dict in attrs:
        tag = soup.find("meta", attrs=attr_dict)
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _extract_all(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else None

    og: dict = {}
    for tag in soup.find_all("meta", property=re.compile(r"^og:")):
        key = tag.get("property", "")[3:]
        if key and tag.get("content"):
            og[key] = tag["content"].strip()

    twitter: dict = {}
    for tag in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:")}):
        key = tag.get("name", "")[8:]
        if key and tag.get("content"):
            twitter[key] = tag["content"].strip()

    description = (
        og.get("description")
        or twitter.get("description")
        or _meta(soup, {"name": "description"})
    )

    canonical = None
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        canonical = link["href"]

    return {
        "url": url,
        "title": og.get("title") or title,
        "description": description,
        "favicon": _extract_favicon(soup, url),
        "canonical": canonical,
        "og": og if og else None,
        "twitter": twitter if twitter else None,
        "html_title": title,
    }


def _make_402(host: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "x402Version": 1, "error": "Payment required",
            "accepts": [{
                "scheme": "exact", "network": NETWORK,
                "maxAmountRequired": PRICE_ATOMIC,
                "resource": f"https://{host}/extract",
                "description": "Extraction des métadonnées OpenGraph / Twitter Card d'une URL",
                "mimeType": "application/json",
                "payTo": PAY_TO, "maxTimeoutSeconds": 300,
                "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
            }],
        },
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/extract" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-social-meta.suretat.com"))
    return await call_next(request)


@app.get("/")
def root():
    return {
        "service": "x402 Social Meta Extractor",
        "protocol": "x402 (Base/USDC)",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoint": "POST /extract",
        "body": {"url": "https://example.com"},
        "extracts": ["title", "description", "favicon", "canonical", "og:*", "twitter:*"],
        "docs": "/docs",
    }


@app.post("/extract")
async def extract(req: MetaRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if not req.url.startswith(("http://", "https://")):
        return JSONResponse(status_code=422, content={"error": "URL invalide (doit commencer par http:// ou https://)"})

    try:
        async with httpx.AsyncClient(
            timeout=min(req.timeout, 15.0),
            follow_redirects=True,
            headers=HEADERS,
        ) as client:
            resp = await client.get(req.url)
            final_url = str(resp.url)
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return JSONResponse(status_code=422, content={
                    "error": f"Type de contenu non supporté : {content_type}",
                    "url": final_url,
                })
            result = _extract_all(resp.text, final_url)
            result["status_code"] = resp.status_code
            return result
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": "Timeout lors de la récupération de l'URL"})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"Erreur réseau : {e}"})


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-social-meta.suretat.com")
    return {"x402Version": 1, "accepts": [{
        "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"https://{host}/extract",
        "description": "Extraction des métadonnées OpenGraph / Twitter Card",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
    }]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3086, proxy_headers=True, forwarded_allow_ips="*")
