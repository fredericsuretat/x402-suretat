from __future__ import annotations
import os, time, hmac, hashlib, base64
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 HMAC", version="1.0.0")

PAID_PATHS = {"/sign", "/verify"}
SUPPORTED_ALGORITHMS = {"sha256", "sha512", "sha1", "md5"}


def _make_402(host: str, endpoint: str = "/sign") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "HMAC signing and verification",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path in PAID_PATHS and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-hmac.suretat.com"), request.url.path)
    return await call_next(request)


class SignRequest(BaseModel):
    message: str
    secret: str
    algorithm: Optional[str] = "sha256"
    encoding: Optional[str] = "hex"  # hex or base64


class VerifyRequest(BaseModel):
    message: str
    secret: str
    signature: str
    algorithm: Optional[str] = "sha256"
    encoding: Optional[str] = "hex"


@app.get("/")
def root():
    return {"service": "x402 HMAC", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/sign")
def sign(req: SignRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    algo = (req.algorithm or "sha256").lower()
    if algo not in SUPPORTED_ALGORITHMS:
        return JSONResponse(status_code=400, content={"error": f"Algorithm must be one of: {', '.join(SUPPORTED_ALGORITHMS)}"})

    encoding = (req.encoding or "hex").lower()

    try:
        key = req.secret.encode("utf-8")
        msg = req.message.encode("utf-8")
        h = hmac.new(key, msg, getattr(hashlib, algo))
        digest = h.digest()

        if encoding == "base64":
            sig = base64.b64encode(digest).decode("utf-8")
        else:
            sig = h.hexdigest()

        return {
            "message": req.message,
            "algorithm": algo,
            "encoding": encoding,
            "signature": sig,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/verify")
def verify(req: VerifyRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    algo = (req.algorithm or "sha256").lower()
    if algo not in SUPPORTED_ALGORITHMS:
        return JSONResponse(status_code=400, content={"error": f"Algorithm must be one of: {', '.join(SUPPORTED_ALGORITHMS)}"})

    encoding = (req.encoding or "hex").lower()

    try:
        key = req.secret.encode("utf-8")
        msg = req.message.encode("utf-8")
        h = hmac.new(key, msg, getattr(hashlib, algo))
        digest = h.digest()

        if encoding == "base64":
            expected = base64.b64encode(digest).decode("utf-8")
        else:
            expected = h.hexdigest()

        # Constant-time comparison
        is_valid = hmac.compare_digest(expected, req.signature)

        return {
            "message": req.message,
            "algorithm": algo,
            "encoding": encoding,
            "is_valid": is_valid,
            "expected": expected,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-hmac.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/sign",
        "description": "HMAC signing and verification",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3101, proxy_headers=True, forwarded_allow_ips="*")
