from __future__ import annotations
import hashlib
import os
import time

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
HIBP_API_KEY = os.getenv("HIBP_API_KEY", "")

HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"
HIBP_EMAIL_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/{email}"

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 HaveIBeenPwned Checker", version="1.0.0")

PAID_PATHS = {"/check-password", "/check-email"}


class PasswordRequest(BaseModel):
    password: str


class EmailRequest(BaseModel):
    email: str
    truncate_response: bool = True


def _k_anonymity_check(password: str) -> dict:
    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix = sha1[:5]
    suffix = sha1[5:]
    return {"sha1_prefix": prefix, "sha1_suffix": suffix}


def _make_402(host: str, path: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "x402Version": 1, "error": "Payment required",
            "accepts": [{
                "scheme": "exact", "network": NETWORK,
                "maxAmountRequired": PRICE_ATOMIC,
                "resource": f"https://{host}{path}",
                "description": "Vérification de compromission de mot de passe ou email (HaveIBeenPwned)",
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
                request.headers.get("host", "x402-pwned.suretat.com"),
                request.url.path,
            )
    return await call_next(request)


@app.get("/")
def root():
    return {
        "service": "x402 HaveIBeenPwned Checker",
        "protocol": "x402 (Base/USDC)",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoints": {
            "POST /check-password": "Vérifier si un mot de passe a été compromis (k-anonymity, aucun envoi du password)",
            "POST /check-email": "Vérifier si un email figure dans des fuites (nécessite HIBP_API_KEY)",
        },
        "privacy": "Le mot de passe n'est jamais transmis — uniquement les 5 premiers caractères du SHA1 (k-anonymity RFC)",
        "source": "HaveIBeenPwned.com",
        "docs": "/docs",
    }


@app.post("/check-password")
async def check_password(req: PasswordRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if not req.password:
        return JSONResponse(status_code=422, content={"error": "password requis"})

    hashes = _k_anonymity_check(req.password)
    prefix, suffix = hashes["sha1_prefix"], hashes["sha1_suffix"]

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                HIBP_RANGE_URL.format(prefix=prefix),
                headers={"Add-Padding": "true"},
            )
            resp.raise_for_status()
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": "HIBP API timeout"})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"Erreur HIBP : {e}"})

    # Chercher le suffix dans la réponse
    count = 0
    found = False
    for line in resp.text.splitlines():
        parts = line.split(":")
        if len(parts) == 2:
            h_suffix, h_count = parts
            if h_suffix.strip().upper() == suffix:
                found = True
                count = int(h_count.strip())
                break

    return {
        "pwned": found,
        "breach_count": count if found else 0,
        "sha1_prefix": prefix,
        "risk_level": (
            "critical" if count > 100000 else
            "high" if count > 10000 else
            "medium" if count > 100 else
            "low" if found else
            "none"
        ),
        "recommendation": (
            "Changez ce mot de passe immédiatement — compromis massivement" if count > 10000
            else "Changez ce mot de passe — il a été trouvé dans des fuites" if found
            else "Mot de passe non trouvé dans les bases de fuites connues"
        ),
        "privacy_note": "Seuls les 5 premiers caractères du SHA1 ont été transmis (k-anonymity)",
    }


@app.post("/check-email")
async def check_email(req: EmailRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if not HIBP_API_KEY:
        return JSONResponse(status_code=503, content={
            "error": "HIBP_API_KEY non configurée",
            "detail": "La vérification d'email nécessite une clé API HIBP (haveibeenpwned.com)",
        })

    if not req.email or "@" not in req.email:
        return JSONResponse(status_code=422, content={"error": "email invalide"})

    headers = {
        "hibp-api-key": HIBP_API_KEY,
        "User-Agent": "x402-pwned/1.0",
    }
    params = {"truncateResponse": str(req.truncate_response).lower()}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                HIBP_EMAIL_URL.format(email=req.email),
                headers=headers,
                params=params,
            )
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": "HIBP API timeout"})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"Erreur HIBP : {e}"})

    if resp.status_code == 404:
        return {"email": req.email, "pwned": False, "breach_count": 0, "breaches": []}
    elif resp.status_code == 401:
        return JSONResponse(status_code=500, content={"error": "Clé API HIBP invalide"})
    elif resp.status_code == 429:
        return JSONResponse(status_code=429, content={"error": "Rate limit HIBP atteint — réessayez dans quelques secondes"})
    elif resp.status_code == 200:
        breaches = resp.json()
        return {
            "email": req.email,
            "pwned": True,
            "breach_count": len(breaches),
            "breaches": breaches,
        }
    else:
        return JSONResponse(status_code=502, content={"error": f"HIBP a répondu {resp.status_code}"})


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-pwned.suretat.com")
    return {"x402Version": 1, "accepts": [{
        "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"https://{host}/check-password",
        "description": "Vérification de compromission de mot de passe (HaveIBeenPwned k-anonymity)",
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
    uvicorn.run(app, host="0.0.0.0", port=3091, proxy_headers=True, forwarded_allow_ips="*")
