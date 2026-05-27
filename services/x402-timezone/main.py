from __future__ import annotations
import logging
import os
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, available_timezones
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-timezone")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Timezone Converter", version="1.0.0")

COMMON_ZONES = [
    "UTC", "Europe/Paris", "Europe/London", "Europe/Berlin", "Europe/Madrid",
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
    "America/Sao_Paulo", "America/Toronto", "America/Mexico_City",
    "Asia/Tokyo", "Asia/Shanghai", "Asia/Kolkata", "Asia/Singapore", "Asia/Dubai",
    "Australia/Sydney", "Pacific/Auckland", "Africa/Cairo", "Africa/Johannesburg",
]


class ConvertRequest(BaseModel):
    datetime_str: str | None = Field(default=None, description="Date/heure ISO 8601 (ex: '2026-05-26T14:30:00'). Si omis: maintenant.")
    from_tz: str = Field(default="UTC", description="Fuseau source (ex: 'Europe/Paris', 'UTC', 'America/New_York')")
    to_tzs: list[str] = Field(
        default=["Europe/Paris", "America/New_York", "Asia/Tokyo", "UTC"],
        description="Fuseaux cibles (max 15)",
        max_length=15,
    )


class NowRequest(BaseModel):
    zones: list[str] = Field(
        default=COMMON_ZONES,
        description="Fuseaux à afficher (max 20)",
        max_length=20,
    )


@app.get("/")
def root():
    return {
        "service": "x402 Timezone Converter",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/conversion",
        "endpoints": {
            "POST /convert": "Convertir une date/heure entre fuseaux",
            "POST /now": "Heure actuelle dans plusieurs fuseaux",
            "GET /zones": "Liste des fuseaux courants",
        },
        "docs": "/docs",
        "tagline": "Convert datetimes between timezones — supports all IANA zones",
        "curl_example": "curl https://x402-timezone.suretat.com/convert -H 'Content-Type: application/json' -d '{\"datetime\": \"2024-01-15T09:00:00\", \"from\": \"UTC\", \"to\": \"Europe/Paris\"}'",
        "try_it": "https://x402-timezone.suretat.com/docs",
    }


@app.get("/zones")
def list_zones():
    return {"fuseaux_courants": COMMON_ZONES, "total_disponibles": len(available_timezones())}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path in ("/convert", "/now") and request.method == "POST":
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
                        "description": "Timezone conversion — 0.0005 USDC",
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


def _parse_dt(dt_str: str | None, from_tz_str: str) -> tuple[datetime, str]:
    try:
        from_tz = ZoneInfo(from_tz_str)
    except Exception:
        raise ValueError(f"Fuseau invalide: {from_tz_str}")

    if dt_str is None:
        dt = datetime.now(tz=from_tz)
    else:
        try:
            dt = datetime.fromisoformat(dt_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=from_tz)
            else:
                dt = dt.astimezone(from_tz)
        except ValueError as e:
            raise ValueError(f"Format date invalide: {dt_str}. Utiliser ISO 8601 (ex: '2026-05-26T14:30:00')")

    return dt, from_tz_str


@app.post("/convert")
def convert_timezone(req: ConvertRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        dt, from_tz_name = _parse_dt(req.datetime_str, req.from_tz)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

    results = {}
    for tz_str in req.to_tzs[:15]:
        try:
            tz = ZoneInfo(tz_str)
            converted = dt.astimezone(tz)
            offset = converted.utcoffset()
            offset_hours = offset.total_seconds() / 3600 if offset else 0
            results[tz_str] = {
                "datetime": converted.strftime("%Y-%m-%dT%H:%M:%S"),
                "datetime_display": converted.strftime("%d/%m/%Y %H:%M:%S %Z"),
                "offset_utc": f"UTC{'+' if offset_hours >= 0 else ''}{offset_hours:g}",
                "timestamp_unix": int(converted.timestamp()),
            }
        except Exception as e:
            results[tz_str] = {"erreur": str(e)}

    # Source info
    utc_dt = dt.astimezone(timezone.utc)
    return {
        "source": {
            "datetime": dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "fuseau": from_tz_name,
            "utc": utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "timestamp_unix": int(dt.timestamp()),
        },
        "conversions": results,
    }


@app.post("/now")
def now_in_zones(req: NowRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    utc_now = datetime.now(timezone.utc)
    results = {}
    for tz_str in req.zones[:20]:
        try:
            tz = ZoneInfo(tz_str)
            local = utc_now.astimezone(tz)
            offset = local.utcoffset()
            offset_hours = offset.total_seconds() / 3600 if offset else 0
            results[tz_str] = {
                "datetime": local.strftime("%Y-%m-%dT%H:%M:%S"),
                "display": local.strftime("%d/%m/%Y %H:%M"),
                "jour_semaine": local.strftime("%A"),
                "offset_utc": f"UTC{'+' if offset_hours >= 0 else ''}{offset_hours:g}",
            }
        except Exception as e:
            results[tz_str] = {"erreur": str(e)}

    return {
        "utc": utc_now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timestamp": int(utc_now.timestamp()),
        "fuseaux": results,
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
            "resource": f"https://{host}/api",
            "description": "x402 Timezone Converter",
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
    uvicorn.run(app, host="0.0.0.0", port=3056)
