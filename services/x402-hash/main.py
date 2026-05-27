from __future__ import annotations
import hashlib
import hmac
import logging
import os
import time
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-hash")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

ALGOS = ["md5", "sha1", "sha224", "sha256", "sha384", "sha512", "sha3_256", "sha3_512", "blake2b", "blake2s"]

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Hash Calculator", version="1.0.0")


class HashRequest(BaseModel):
    text: str = Field(..., description="Texte à hasher", max_length=100_000)
    algos: list[str] = Field(
        default=["md5", "sha1", "sha256"],
        description=f"Algorithmes à utiliser: {', '.join(ALGOS)}",
    )
    encoding: Literal["utf-8", "latin-1", "ascii"] = Field(default="utf-8")
    hmac_key: str | None = Field(default=None, description="Clé HMAC (optionnel — retourne HMAC-SHA256)")
    uppercase: bool = Field(default=False, description="Résultats en majuscules")


@app.get("/")
def root():
    return {
        "service": "x402 Hash Calculator",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/appel",
        "endpoint": "POST /hash",
        "algorithmes": ALGOS,
        "docs": "/docs",
        "tagline": "Compute cryptographic hashes (MD5, SHA256, BLAKE2...) in one API call",
        "curl_example": "curl https://x402-hash.suretat.com/hash -H 'Content-Type: application/json' -d '{\"text\": \"hello world\", \"algos\": [\"sha256\", \"md5\"]}'",
        "try_it": "https://x402-hash.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/hash" and request.method == "POST":
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
                        "description": "Hash Calculator — 0.0005 USDC",
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


@app.post("/hash")
def compute_hash(req: HashRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        data = req.text.encode(req.encoding)
    except (UnicodeEncodeError, LookupError) as e:
        return JSONResponse(status_code=400, content={"error": f"Encoding error: {e}"})

    results: dict = {}
    for algo in req.algos:
        if algo not in ALGOS:
            results[algo] = {"error": f"Algorithme non supporté. Supportés: {ALGOS}"}
            continue
        try:
            h = hashlib.new(algo, data)
            digest = h.hexdigest()
            results[algo] = digest.upper() if req.uppercase else digest
        except Exception as e:
            results[algo] = {"error": str(e)}

    response: dict = {
        "text_length": len(req.text),
        "encoding": req.encoding,
        "hashes": results,
    }

    if req.hmac_key:
        key = req.hmac_key.encode("utf-8")
        hmac_val = hmac.new(key, data, hashlib.sha256).hexdigest()
        response["hmac_sha256"] = hmac_val.upper() if req.uppercase else hmac_val

    return response



@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK if "NETWORK" in dir() else os.getenv("NETWORK", "base"),
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/hash",
            "description": "x402 Hash Calculator",
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
    uvicorn.run(app, host="0.0.0.0", port=3046)
