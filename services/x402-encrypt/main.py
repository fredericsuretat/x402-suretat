from __future__ import annotations
import os, time, base64, secrets
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Encrypt", version="1.0.0")

PAID_PATHS = {"/encrypt", "/decrypt"}


def _make_402(host: str, endpoint: str = "/encrypt") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "AES-256-GCM encryption and decryption",
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
            return _make_402(request.headers.get("host", "x402-encrypt.suretat.com"), request.url.path)
    return await call_next(request)


class EncryptRequest(BaseModel):
    data: str
    key: Optional[str] = None  # hex 32 bytes or None to auto-generate


class DecryptRequest(BaseModel):
    ciphertext_b64: str
    key_hex: str
    nonce_b64: str
    tag_b64: str


@app.get("/")
def root():
    return {"service": "x402 Encrypt", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/encrypt")
def encrypt(req: EncryptRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    # Get or generate key
    if req.key:
        try:
            key = bytes.fromhex(req.key)
            if len(key) != 32:
                return JSONResponse(status_code=400, content={"error": "Key must be exactly 32 bytes (64 hex chars)"})
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "Invalid hex key"})
    else:
        key = get_random_bytes(32)

    # Encrypt
    nonce = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

    # Try to detect if data is base64, else treat as text
    try:
        plaintext = base64.b64decode(req.data)
    except Exception:
        plaintext = req.data.encode("utf-8")

    ciphertext, tag = cipher.encrypt_and_digest(plaintext)

    return {
        "ciphertext_b64": base64.b64encode(ciphertext).decode("utf-8"),
        "key_hex": key.hex(),
        "nonce_b64": base64.b64encode(nonce).decode("utf-8"),
        "tag_b64": base64.b64encode(tag).decode("utf-8"),
        "original_length": len(plaintext),
    }


@app.post("/decrypt")
def decrypt(req: DecryptRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        key = bytes.fromhex(req.key_hex)
        if len(key) != 32:
            return JSONResponse(status_code=400, content={"error": "Key must be exactly 32 bytes"})
        nonce = base64.b64decode(req.nonce_b64)
        tag = base64.b64decode(req.tag_b64)
        ciphertext = base64.b64decode(req.ciphertext_b64)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Invalid input: {str(e)}"})

    try:
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": "Decryption failed: invalid key or corrupted data"})

    # Try to decode as UTF-8 text, else return base64
    try:
        text = plaintext.decode("utf-8")
        return {"data": text, "encoding": "text", "length": len(plaintext)}
    except UnicodeDecodeError:
        return {"data": base64.b64encode(plaintext).decode("utf-8"), "encoding": "base64", "length": len(plaintext)}


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-encrypt.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/encrypt",
        "description": "AES-256-GCM encryption and decryption",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3102, proxy_headers=True, forwarded_allow_ips="*")
