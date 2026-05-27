from __future__ import annotations
import logging
import os
import time

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from markdownify import markdownify as md
from pydantic import BaseModel, Field
from readability import Document

log = logging.getLogger("x402-html2md")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
TIMEOUT       = int(os.getenv("FETCH_TIMEOUT", "15"))

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 HTML to Markdown", version="1.0.0")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; x402-html2md/1.0; +https://x402-html2md.suretat.com)",
    "Accept": "text/html,application/xhtml+xml",
}


class ExtractRequest(BaseModel):
    url: str | None = Field(default=None, description="URL to fetch and extract")
    html: str | None = Field(default=None, description="Raw HTML to extract (alternative to url)")
    include_links: bool = Field(default=True, description="Keep hyperlinks in Markdown")
    include_images: bool = Field(default=False, description="Keep image references")


@app.get("/")
def root():
    return {
        "service": "x402 HTML to Markdown",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoint": "POST /extract",
        "tagline": "Extract clean Markdown from any URL or HTML — powered by Readability",
        "curl_example": "curl https://x402-html2md.suretat.com/extract -H 'Content-Type: application/json' -d '{\"url\": \"https://example.com\"}'",
        "try_it": "https://x402-html2md.suretat.com/docs",
        "docs": "/docs",
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
                        "resource": "https://" + request.headers.get("host", "") + "/extract",
                        "description": "Extract clean Markdown from any URL",
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
async def extract(req: ExtractRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if not req.url and not req.html:
        return JSONResponse(status_code=400, content={"error": "Provide either 'url' or 'html'"})

    raw_html = req.html
    final_url = req.url or ""

    if req.url:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=HEADERS) as client:
                resp = await client.get(req.url)
                resp.raise_for_status()
                raw_html = resp.text
                final_url = str(resp.url)
        except httpx.TimeoutException:
            return JSONResponse(status_code=408, content={"error": f"Request timed out after {TIMEOUT}s"})
        except httpx.HTTPStatusError as e:
            return JSONResponse(status_code=502, content={"error": f"HTTP {e.response.status_code} from {req.url}"})
        except Exception as e:
            return JSONResponse(status_code=502, content={"error": str(e)})

    try:
        doc = Document(raw_html, url=final_url)
        title = doc.title()
        content_html = doc.summary(html_partial=True)
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Readability failed: {e}"})

    md_options: dict = {
        "heading_style": "ATX",
        "strip": [] if req.include_images else ["img"],
    }
    if not req.include_links:
        md_options["convert_links"] = lambda el, text, **kw: text

    markdown = md(content_html, **md_options).strip()

    return {
        "title": title,
        "url": final_url,
        "markdown": markdown,
        "length": len(markdown),
        "word_count": len(markdown.split()),
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-html2md.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/extract",
            "description": "Extract clean Markdown from any URL",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3070, proxy_headers=True, forwarded_allow_ips="*")
