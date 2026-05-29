from __future__ import annotations
import os, time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import httpx

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Headers", version="1.0.0")


def _make_402(host: str, endpoint: str = "/fetch") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "Fetch HTTP headers and server info from any URL",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/fetch" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-headers.suretat.com"))
    return await call_next(request)


class FetchRequest(BaseModel):
    url: str
    method: Optional[str] = "HEAD"


@app.get("/")
def root():
    return {"service": "x402 Headers", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/fetch")
async def fetch(req: FetchRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    method = req.method.upper() if req.method else "HEAD"
    if method not in ("HEAD", "GET", "OPTIONS"):
        return JSONResponse(status_code=400, content={"error": "Only HEAD, GET, OPTIONS methods supported"})

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            response = await client.request(method, req.url)

        headers_dict = dict(response.headers)
        server_info = {
            "server": headers_dict.get("server", None),
            "x_powered_by": headers_dict.get("x-powered-by", None),
            "content_type": headers_dict.get("content-type", None),
            "content_length": headers_dict.get("content-length", None),
            "cache_control": headers_dict.get("cache-control", None),
            "etag": headers_dict.get("etag", None),
            "last_modified": headers_dict.get("last-modified", None),
            "strict_transport_security": headers_dict.get("strict-transport-security", None),
            "x_frame_options": headers_dict.get("x-frame-options", None),
            "x_content_type_options": headers_dict.get("x-content-type-options", None),
            "content_security_policy": headers_dict.get("content-security-policy", None),
        }

        return {
            "url": str(response.url),
            "status_code": response.status_code,
            "method": method,
            "headers": headers_dict,
            "server_info": {k: v for k, v in server_info.items() if v is not None},
            "redirect_count": len(response.history),
        }

    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": "Request timed out"})
    except httpx.RequestError as e:
        return JSONResponse(status_code=502, content={"error": f"Request failed: {str(e)}"})


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-headers.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/fetch",
        "description": "Fetch HTTP headers and server info from any URL",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3096, proxy_headers=True, forwarded_allow_ips="*")
