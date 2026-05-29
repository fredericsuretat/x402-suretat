from __future__ import annotations
import base64
import io
import os
import time

import pyotp
import qrcode
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 TOTP Generator & Verifier", version="1.0.0")

PAID_PATHS = {"/generate", "/verify", "/create-secret"}


class GenerateRequest(BaseModel):
    secret: str
    digits: int = Field(default=6, ge=6, le=8)
    period: int = Field(default=30, ge=15, le=120)
    issuer: Optional[str] = None
    account: Optional[str] = None


class VerifyRequest(BaseModel):
    secret: str
    code: str
    digits: int = Field(default=6, ge=6, le=8)
    period: int = Field(default=30, ge=15, le=120)
    valid_window: int = Field(default=1, ge=0, le=5)


class CreateSecretRequest(BaseModel):
    issuer: str = "x402"
    account: str = "user@example.com"
    digits: int = Field(default=6, ge=6, le=8)
    period: int = Field(default=30, ge=15, le=120)


def _make_qr_b64(uri: str) -> str:
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _make_402(host: str, path: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "x402Version": 1, "error": "Payment required",
            "accepts": [{
                "scheme": "exact", "network": NETWORK,
                "maxAmountRequired": PRICE_ATOMIC,
                "resource": f"https://{host}{path}",
                "description": "Génération / vérification de codes TOTP (RFC 6238)",
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
    if request.url.path in PAID_PATHS and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(
                request.headers.get("host", "x402-totp.suretat.com"),
                request.url.path,
            )
    return await call_next(request)


@app.get("/")
def root():
    return {
        "service": "x402 TOTP Generator & Verifier",
        "protocol": "x402 (Base/USDC)",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoints": {
            "POST /create-secret": "Créer un nouveau secret TOTP + QR code",
            "POST /generate": "Générer le code TOTP actuel depuis un secret",
            "POST /verify": "Vérifier un code TOTP",
        },
        "docs": "/docs",
    }


@app.post("/create-secret")
def create_secret(req: CreateSecretRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret, digits=req.digits, interval=req.period)
    uri = totp.provisioning_uri(name=req.account, issuer_name=req.issuer)
    return {
        "secret": secret,
        "digits": req.digits,
        "period": req.period,
        "issuer": req.issuer,
        "account": req.account,
        "provisioning_uri": uri,
        "qr_code_base64": _make_qr_b64(uri),
        "current_code": totp.now(),
    }


@app.post("/generate")
def generate(req: GenerateRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    try:
        totp = pyotp.TOTP(req.secret, digits=req.digits, interval=req.period)
        now_ts = int(time.time())
        code = totp.now()
        time_remaining = req.period - (now_ts % req.period)
        result: dict = {
            "code": code,
            "digits": req.digits,
            "period": req.period,
            "time_remaining_seconds": time_remaining,
            "timestamp": now_ts,
        }
        if req.issuer and req.account:
            uri = totp.provisioning_uri(name=req.account, issuer_name=req.issuer)
            result["provisioning_uri"] = uri
            result["qr_code_base64"] = _make_qr_b64(uri)
        return result
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Secret invalide : {e}"})


@app.post("/verify")
def verify(req: VerifyRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    try:
        totp = pyotp.TOTP(req.secret, digits=req.digits, interval=req.period)
        code_clean = req.code.strip().replace(" ", "")
        valid = totp.verify(code_clean, valid_window=req.valid_window)
        return {
            "valid": valid,
            "code_provided": code_clean,
            "current_code": totp.now(),
            "valid_window": req.valid_window,
            "period": req.period,
        }
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Secret invalide : {e}"})


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-totp.suretat.com")
    return {"x402Version": 1, "accepts": [{
        "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"https://{host}/generate",
        "description": "Génération / vérification de codes TOTP (RFC 6238)",
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
    uvicorn.run(app, host="0.0.0.0", port=3087, proxy_headers=True, forwarded_allow_ips="*")
