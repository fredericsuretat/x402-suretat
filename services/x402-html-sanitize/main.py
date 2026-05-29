from __future__ import annotations
import os, time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import bleach

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 HTML Sanitize", version="1.0.0")

DEFAULT_ALLOWED_TAGS = ["p", "b", "i", "a", "ul", "ol", "li", "br", "strong", "em", "span", "div", "h1", "h2", "h3", "blockquote", "code", "pre"]
DEFAULT_ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "*": ["class"],
}


def _make_402(host: str, endpoint: str = "/sanitize") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "HTML sanitization, XSS removal and tag filtering",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/sanitize" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-html-sanitize.suretat.com"))
    return await call_next(request)


class SanitizeRequest(BaseModel):
    html: str
    allow_tags: Optional[List[str]] = None
    allow_attrs: Optional[dict] = None
    strip: Optional[bool] = True


@app.get("/")
def root():
    return {"service": "x402 HTML Sanitize", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/sanitize")
def sanitize(req: SanitizeRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    allowed_tags = req.allow_tags if req.allow_tags is not None else DEFAULT_ALLOWED_TAGS
    allowed_attrs = req.allow_attrs if req.allow_attrs is not None else DEFAULT_ALLOWED_ATTRS

    original_len = len(req.html)

    try:
        cleaned = bleach.clean(
            req.html,
            tags=allowed_tags,
            attributes=allowed_attrs,
            strip=req.strip if req.strip is not None else True,
        )
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Sanitization failed: {str(e)}"})

    cleaned_len = len(cleaned)
    removed_bytes = original_len - cleaned_len

    return {
        "sanitized": cleaned,
        "original_length": original_len,
        "sanitized_length": cleaned_len,
        "removed_bytes": removed_bytes,
        "allowed_tags": allowed_tags,
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-html-sanitize.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/sanitize",
        "description": "HTML sanitization, XSS removal and tag filtering",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3099, proxy_headers=True, forwarded_allow_ips="*")
