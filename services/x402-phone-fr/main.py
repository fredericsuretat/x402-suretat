from __future__ import annotations
import logging
import os
import time
from typing import Literal

import phonenumbers
from phonenumbers import geocoder, carrier, timezone
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-phone-fr")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

TYPE_MAP = {
    phonenumbers.PhoneNumberType.FIXED_LINE: "Fixe",
    phonenumbers.PhoneNumberType.MOBILE: "Mobile",
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "Fixe ou mobile",
    phonenumbers.PhoneNumberType.TOLL_FREE: "Numéro vert",
    phonenumbers.PhoneNumberType.PREMIUM_RATE: "Surtaxé",
    phonenumbers.PhoneNumberType.SHARED_COST: "Coût partagé",
    phonenumbers.PhoneNumberType.VOIP: "VoIP",
    phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "Personnel",
    phonenumbers.PhoneNumberType.PAGER: "Pager",
    phonenumbers.PhoneNumberType.UAN: "UAN",
    phonenumbers.PhoneNumberType.UNKNOWN: "Inconnu",
}

app = FastAPI(title="x402 Phone Validator FR", version="1.0.0")


class PhoneRequest(BaseModel):
    numero: str = Field(..., description="Numéro de téléphone à valider", examples=["0612345678", "+33612345678"])
    pays: str = Field(default="FR", description="Code pays ISO (défaut: FR pour numéros sans +)")


@app.get("/")
def root():
    return {
        "service": "x402 Phone Validator FR",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/validation",
        "endpoint": "POST /validate",
        "fonctionnalites": ["validation RFC", "format E.164/international/national", "type (mobile/fixe/VoIP)", "opérateur", "région", "timezone"],
        "docs": "/docs",
        "tagline": "Validate and format French phone numbers — returns operator and type",
        "curl_example": "curl https://x402-phone-fr.suretat.com/validate -H 'Content-Type: application/json' -d '{\"phone\": \"0612345678\"}'",
        "try_it": "https://x402-phone-fr.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/validate" and request.method == "POST":
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
                        "description": "Phone validation — 0.0005 USDC",
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


@app.post("/validate")
def validate_phone(req: PhoneRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        parsed = phonenumbers.parse(req.numero, req.pays)
    except phonenumbers.NumberParseException as e:
        return JSONResponse(
            status_code=400,
            content={"valide": False, "numero": req.numero, "erreur": str(e)},
        )

    valide = phonenumbers.is_valid_number(parsed)
    possible = phonenumbers.is_possible_number(parsed)
    num_type = phonenumbers.number_type(parsed)
    country_code = phonenumbers.region_code_for_number(parsed)

    return {
        "numero_saisi": req.numero,
        "valide": valide,
        "possible": possible,
        "format_e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164) if valide else None,
        "format_international": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL) if valide else None,
        "format_national": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL) if valide else None,
        "indicatif_pays": f"+{parsed.country_code}",
        "numero_national": str(parsed.national_number),
        "code_pays": country_code,
        "type": TYPE_MAP.get(num_type, "Inconnu"),
        "region": geocoder.description_for_number(parsed, "fr") or None,
        "operateur": carrier.name_for_number(parsed, "fr") or None,
        "timezones": list(timezone.time_zones_for_number(parsed)),
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
            "resource": f"https://{host}/validate",
            "description": "x402 Phone Validator FR",
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
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3048)
