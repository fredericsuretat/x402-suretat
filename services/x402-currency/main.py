from __future__ import annotations
import logging
import os
import time
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-currency")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

# Frankfurter.app — free, no API key, ECB data updated daily
RATES_API = "https://api.frankfurter.app"

# Cache rates for 1 hour
_rate_cache: dict[str, Any] = {}
_cache_time: float = 0.0
CACHE_TTL = 3600

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Currency Converter", version="1.0.0")


class ConvertRequest(BaseModel):
    amount: float = Field(default=1.0, description="Montant à convertir")
    from_currency: str = Field(default="EUR", description="Devise source (ISO 4217)")
    to_currencies: list[str] = Field(
        default=["USD", "GBP", "CHF", "JPY", "CAD"],
        description="Devises cibles (max 10)",
        max_length=10,
    )


async def _get_rates(base: str) -> dict[str, float]:
    global _rate_cache, _cache_time
    cache_key = base.upper()
    now = time.time()

    if cache_key in _rate_cache and now - _cache_time < CACHE_TTL:
        return _rate_cache[cache_key]

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{RATES_API}/latest?base={cache_key}")
        data = r.json()

    rates = data.get("rates", {})
    _rate_cache[cache_key] = rates
    _cache_time = now
    return rates


@app.get("/")
def root():
    return {
        "service": "x402 Currency Converter",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/conversion",
        "endpoint": "POST /convert",
        "source": "Frankfurter.app (BCE)",
        "update": "quotidien (jours ouvrés BCE)",
        "docs": "/docs",
        "tagline": "Live currency conversion — 170+ currencies via ECB rates",
        "curl_example": "curl https://x402-currency.suretat.com/convert -H 'Content-Type: application/json' -d '{\"amount\": 100, \"from_currency\": \"EUR\", \"to_currency\": \"USD\"}'",
        "try_it": "https://x402-currency.suretat.com/docs",
    }


@app.get("/currencies")
async def list_currencies():
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{RATES_API}/currencies")
        return r.json()


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/convert" and request.method == "POST":
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
                        "description": "Currency conversion — 0.0005 USDC",
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


@app.post("/convert")
async def convert(req: ConvertRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    base = req.from_currency.upper()
    targets = [t.upper() for t in req.to_currencies[:10]]

    try:
        rates = await _get_rates(base)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"API taux de change: {e}"})

    conversions = {}
    for target in targets:
        if target == base:
            conversions[target] = {"montant": req.amount, "taux": 1.0}
        elif target in rates:
            rate = rates[target]
            conversions[target] = {
                "montant": round(req.amount * rate, 6),
                "taux": rate,
            }
        else:
            conversions[target] = {"erreur": f"Devise inconnue: {target}"}

    return {
        "montant_source": req.amount,
        "devise_source": base,
        "date_taux": time.strftime("%Y-%m-%d", time.gmtime(_cache_time)) if _cache_time else "inconnu",
        "source_donnees": "Banque Centrale Européenne (via Frankfurter.app)",
        "conversions": conversions,
    }



@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK if "NETWORK" in dir() else os.getenv("NETWORK", "base"),
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/convert",
            "description": "x402 Currency Converter",
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
    uvicorn.run(app, host="0.0.0.0", port=3051)
