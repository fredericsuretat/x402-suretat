from __future__ import annotations
import logging
import os
import time

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-ipgeo")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 IP Geolocation", version="1.0.0")


class IPRequest(BaseModel):
    ip: str = Field(..., description="Adresse IP à géolocaliser (IPv4 ou IPv6)", examples=["8.8.8.8"])
    lang: str = Field(default="fr", description="Langue de la réponse (fr, en, de, es, pt, ru, ja, zh-CN)")


@app.get("/")
def root():
    return {
        "service": "x402 IP Geolocation",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.001 USDC/lookup",
        "endpoint": "POST /lookup",
        "features": ["pays", "ville", "FAI/ASN", "timezone", "coordonnées GPS", "proxy/VPN détection"],
        "docs": "/docs",
        "tagline": "Geolocate any IP address — country, city, coordinates, ISP",
        "curl_example": "curl https://x402-ipgeo.suretat.com/geo?ip=8.8.8.8",
        "try_it": "https://x402-ipgeo.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/lookup" and request.method == "POST":
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
                        "description": "IP Geolocation lookup — 0.001 USDC",
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


@app.post("/lookup")
async def lookup_ip(req: IPRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    lang_map = {"fr": "fr", "en": "en", "de": "de", "es": "es", "pt": "pt-BR", "ru": "ru", "ja": "ja", "zh": "zh-CN"}
    lang = lang_map.get(req.lang, "fr")

    url = f"http://ip-api.com/json/{req.ip}?fields=status,message,country,countryCode,region,regionName,city,zip,lat,lon,timezone,isp,org,as,asname,reverse,mobile,proxy,hosting,query&lang={lang}"

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        data = r.json()

    if data.get("status") == "fail":
        return JSONResponse(status_code=400, content={"error": data.get("message", "Lookup failed"), "ip": req.ip})

    return {
        "ip": data.get("query"),
        "pays": data.get("country"),
        "code_pays": data.get("countryCode"),
        "region": data.get("regionName"),
        "code_region": data.get("region"),
        "ville": data.get("city"),
        "code_postal": data.get("zip"),
        "latitude": data.get("lat"),
        "longitude": data.get("lon"),
        "timezone": data.get("timezone"),
        "fai": data.get("isp"),
        "organisation": data.get("org"),
        "asn": data.get("as"),
        "asn_nom": data.get("asname"),
        "dns_inverse": data.get("reverse"),
        "mobile": data.get("mobile", False),
        "proxy_vpn": data.get("proxy", False),
        "datacenter_hosting": data.get("hosting", False),
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
            "resource": f"https://{host}/lookup",
            "description": "x402 IP Geolocation",
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
    uvicorn.run(app, host="0.0.0.0", port=3043)
