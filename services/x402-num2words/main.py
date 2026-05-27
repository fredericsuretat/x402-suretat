from __future__ import annotations
import logging
import os
import time
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from num2words import num2words
from pydantic import BaseModel, Field

log = logging.getLogger("x402-num2words")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

SUPPORTED_LANGS = ["fr", "fr_BE", "fr_CH", "en", "de", "es", "it", "pt", "nl", "pl", "ru", "ar", "ja"]

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Nombre en Lettres", version="1.0.0")


class Num2WordsRequest(BaseModel):
    number: float = Field(..., description="Nombre à convertir", examples=[1234.56])
    lang: str = Field(default="fr", description=f"Langue: {', '.join(SUPPORTED_LANGS)}")
    to: Literal["cardinal", "ordinal", "ordinal_num", "year", "currency"] = Field(
        default="cardinal",
        description="Type de conversion: cardinal (un, deux…), ordinal (premier, deuxième…), year, currency"
    )
    currency: str = Field(default="EUR", description="Code devise ISO 4217 (pour to=currency)")


@app.get("/")
def root():
    return {
        "service": "x402 Nombre en Lettres",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/conversion",
        "endpoint": "POST /convert",
        "langues": SUPPORTED_LANGS,
        "types": ["cardinal", "ordinal", "ordinal_num", "year", "currency"],
        "docs": "/docs",
        "example": {"number": 1234.56, "lang": "fr", "to": "currency", "currency": "EUR"},
        "tagline": "Convert numbers to words in French and other languages",
        "curl_example": "curl https://x402-num2words.suretat.com/convert -H 'Content-Type: application/json' -d '{\"number\": 42, \"lang\": \"fr\", \"ordinal\": false}'",
        "try_it": "https://x402-num2words.suretat.com/docs",
    }


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
                        "description": "Nombre en lettres — 0.0005 USDC",
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
def convert(req: Num2WordsRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    lang = req.lang if req.lang in SUPPORTED_LANGS else "fr"
    try:
        if req.to == "currency":
            result = num2words(req.number, lang=lang, to="currency", currency=req.currency)
        else:
            value = int(req.number) if req.to in ("ordinal", "ordinal_num", "year") else req.number
            result = num2words(value, lang=lang, to=req.to)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e), "number": req.number})

    return {
        "number": req.number,
        "text": result,
        "lang": lang,
        "type": req.to,
        "currency": req.currency if req.to == "currency" else None,
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
            "description": "x402 Nombre en Lettres",
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
    uvicorn.run(app, host="0.0.0.0", port=3044)
