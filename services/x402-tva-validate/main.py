from __future__ import annotations
import os
import re
import time

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
VIES_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{cc}/vat/{number}"

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 TVA Validator", version="1.0.0")

# Formats de numéros TVA par pays (regex sur la partie après le code pays)
VAT_FORMATS: dict[str, str] = {
    "AT": r"U\d{8}",
    "BE": r"0\d{9}",
    "BG": r"\d{9,10}",
    "CY": r"\d{8}[A-Z]",
    "CZ": r"\d{8,10}",
    "DE": r"\d{9}",
    "DK": r"\d{8}",
    "EE": r"\d{9}",
    "EL": r"\d{9}",
    "ES": r"[A-Z0-9]\d{7}[A-Z0-9]",
    "FI": r"\d{8}",
    "FR": r"[A-Z0-9]{2}\d{9}",
    "HR": r"\d{11}",
    "HU": r"\d{8}",
    "IE": r"\d[A-Z0-9+*]\d{5}[A-Z]{1,2}",
    "IT": r"\d{11}",
    "LT": r"(\d{9}|\d{12})",
    "LU": r"\d{8}",
    "LV": r"\d{11}",
    "MT": r"\d{8}",
    "NL": r"\d{9}B\d{2}",
    "PL": r"\d{10}",
    "PT": r"\d{9}",
    "RO": r"\d{2,10}",
    "SE": r"\d{12}",
    "SI": r"\d{8}",
    "SK": r"\d{10}",
    "XI": r"(\d{9}|\d{12}|GD\d{3}|HA\d{3})",
}


def parse_vat(raw: str) -> tuple[str, str] | None:
    cleaned = re.sub(r"[\s.\-]", "", raw.upper().strip())
    if len(cleaned) < 4:
        return None
    cc = cleaned[:2]
    number = cleaned[2:]
    if cc not in VAT_FORMATS:
        return None
    return cc, number


async def check_vies(cc: str, number: str) -> dict:
    url = VIES_URL.format(cc=cc, number=number)
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "valid": data.get("isValid", False),
                    "company_name": data.get("name") or None,
                    "address": data.get("address") or None,
                    "country_code": data.get("countryCode", cc),
                    "request_date": data.get("requestDate") or None,
                    "source": "VIES",
                }
            elif resp.status_code == 404:
                return {"valid": False, "source": "VIES", "detail": "Numéro inconnu"}
        except httpx.TimeoutException:
            return {"valid": None, "source": "timeout", "detail": "VIES indisponible (timeout)"}
        except Exception as e:
            return {"valid": None, "source": "error", "detail": str(e)}
    return {"valid": None, "source": "error", "detail": "Réponse inattendue"}


def _make_402(host: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "x402Version": 1, "error": "Payment required",
            "accepts": [{
                "scheme": "exact", "network": NETWORK,
                "maxAmountRequired": PRICE_ATOMIC,
                "resource": f"https://{host}/validate",
                "description": "Validation numéro TVA intracommunautaire via VIES (UE)",
                "mimeType": "application/json",
                "payTo": PAY_TO, "maxTimeoutSeconds": 300,
                "asset": ASSET_ADDRESS,
                "extra": {"name": "USDC", "version": "2"},
            }],
        },
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/validate" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-tva-validate.suretat.com"))
    return await call_next(request)


class VatRequest(BaseModel):
    vat_number: str


@app.get("/")
def root():
    return {
        "service": "x402 TVA Validator",
        "protocol": "x402 (Base/USDC)",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoint": "POST /validate",
        "body": {"vat_number": "FR12345678901"},
        "supported_countries": sorted(VAT_FORMATS.keys()),
        "docs": "/docs",
    }


@app.post("/validate")
async def validate(req: VatRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    parsed = parse_vat(req.vat_number)
    if not parsed:
        return JSONResponse(status_code=422, content={
            "error": "Format invalide",
            "detail": "Le numéro doit commencer par un code pays UE (ex: FR, DE, ES...)",
            "supported_countries": sorted(VAT_FORMATS.keys()),
        })

    cc, number = parsed
    fmt_re = VAT_FORMATS[cc]
    format_ok = bool(re.fullmatch(fmt_re, number))

    result = await check_vies(cc, number)
    return {
        "input": req.vat_number,
        "country_code": cc,
        "vat_number": number,
        "format_valid": format_ok,
        **result,
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-tva-validate.suretat.com")
    return {"x402Version": 1, "accepts": [{
        "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"https://{host}/validate",
        "description": "Validation numéro TVA intracommunautaire via VIES",
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
    uvicorn.run(app, host="0.0.0.0", port=3085, proxy_headers=True, forwarded_allow_ips="*")
