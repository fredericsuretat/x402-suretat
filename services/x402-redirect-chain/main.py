from __future__ import annotations
import os
import time
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

HEADERS_UA = {
    "User-Agent": "Mozilla/5.0 (compatible; x402-redirect-chain/1.0)",
    "Accept": "text/html,*/*",
}

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Redirect Chain Follower", version="1.0.0")


class FollowRequest(BaseModel):
    url: str
    max_hops: int = Field(default=15, ge=1, le=30)
    timeout: float = Field(default=10.0, ge=1.0, le=20.0)
    include_headers: bool = False


def _make_402(host: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "x402Version": 1, "error": "Payment required",
            "accepts": [{
                "scheme": "exact", "network": NETWORK,
                "maxAmountRequired": PRICE_ATOMIC,
                "resource": f"https://{host}/follow",
                "description": "Suivi de la chaîne de redirections HTTP d'une URL",
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
    if request.url.path == "/follow" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-redirect-chain.suretat.com"))
    return await call_next(request)


@app.get("/")
def root():
    return {
        "service": "x402 Redirect Chain Follower",
        "protocol": "x402 (Base/USDC)",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoint": "POST /follow",
        "body": {"url": "https://bit.ly/xxx", "max_hops": 15},
        "docs": "/docs",
    }


@app.post("/follow")
async def follow(req: FollowRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if not req.url.startswith(("http://", "https://")):
        return JSONResponse(status_code=422, content={"error": "URL invalide"})

    chain = []
    current_url = req.url
    start_ts = time.time()

    async with httpx.AsyncClient(
        timeout=req.timeout,
        follow_redirects=False,
        headers=HEADERS_UA,
    ) as client:
        for hop in range(req.max_hops):
            try:
                resp = await client.get(current_url)
            except httpx.TimeoutException:
                chain.append({
                    "hop": hop + 1,
                    "url": current_url,
                    "error": "timeout",
                })
                break
            except Exception as e:
                chain.append({
                    "hop": hop + 1,
                    "url": current_url,
                    "error": str(e),
                })
                break

            hop_info: dict = {
                "hop": hop + 1,
                "url": current_url,
                "status_code": resp.status_code,
                "server": resp.headers.get("server") or resp.headers.get("Server"),
            }

            if req.include_headers:
                hop_info["headers"] = dict(resp.headers)

            location = resp.headers.get("location") or resp.headers.get("Location")
            if location:
                hop_info["location"] = location
            else:
                hop_info["location"] = None

            chain.append(hop_info)

            if resp.status_code in (301, 302, 303, 307, 308) and location:
                # Résoudre les URLs relatives
                if location.startswith("http"):
                    current_url = location
                else:
                    from urllib.parse import urljoin
                    current_url = urljoin(current_url, location)
            else:
                break

    elapsed = round(time.time() - start_ts, 3)
    final = chain[-1] if chain else None

    return {
        "original_url": req.url,
        "final_url": current_url,
        "hops": len(chain),
        "final_status_code": final["status_code"] if final and "status_code" in final else None,
        "is_redirect_loop": len(chain) >= req.max_hops,
        "elapsed_seconds": elapsed,
        "chain": chain,
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-redirect-chain.suretat.com")
    return {"x402Version": 1, "accepts": [{
        "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"https://{host}/follow",
        "description": "Suivi de la chaîne de redirections HTTP",
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
    uvicorn.run(app, host="0.0.0.0", port=3090, proxy_headers=True, forwarded_allow_ips="*")
