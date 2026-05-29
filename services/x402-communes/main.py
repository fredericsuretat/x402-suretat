from __future__ import annotations
import os
import time
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

GEO_API = "https://geo.api.gouv.fr"
FIELDS = "nom,code,codeDepartement,codeRegion,codesPostaux,population,surface,centre,contour"

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Communes France", version="1.0.0")

PAID_PATHS = {"/commune", "/postal", "/search"}


def _make_402(host: str, path: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "x402Version": 1, "error": "Payment required",
            "accepts": [{
                "scheme": "exact", "network": NETWORK,
                "maxAmountRequired": PRICE_ATOMIC,
                "resource": f"https://{host}/search",
                "description": "Données des communes françaises (INSEE, département, population, code postal...)",
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
    path = request.url.path.split("?")[0]
    is_paid = any(path.startswith(p) for p in PAID_PATHS)
    if is_paid:
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-communes.suretat.com"), path)
    return await call_next(request)


def _format_commune(c: dict) -> dict:
    return {
        "code_insee": c.get("code"),
        "nom": c.get("nom"),
        "codes_postaux": c.get("codesPostaux", []),
        "code_departement": c.get("codeDepartement"),
        "code_region": c.get("codeRegion"),
        "population": c.get("population"),
        "surface_km2": round(c["surface"] / 100, 2) if c.get("surface") else None,
        "centre": c.get("centre"),
    }


@app.get("/")
def root():
    return {
        "service": "x402 Communes France",
        "protocol": "x402 (Base/USDC)",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoints": {
            "GET /commune/{code_insee}": "Données d'une commune par code INSEE (ex: 75056)",
            "GET /postal/{code_postal}": "Communes d'un code postal (ex: 75001)",
            "GET /search?q=...&departement=...&limit=10": "Recherche par nom de commune",
        },
        "source": "geo.api.gouv.fr (données INSEE)",
        "docs": "/docs",
    }


@app.get("/commune/{code_insee}")
async def get_commune(code_insee: str, request: Request, with_contour: bool = False):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    fields = FIELDS + (",contour" if with_contour else "")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{GEO_API}/communes/{code_insee}", params={"fields": fields})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"API indisponible : {e}"})

    if resp.status_code == 404:
        return JSONResponse(status_code=404, content={"error": f"Commune '{code_insee}' introuvable"})
    if resp.status_code != 200:
        return JSONResponse(status_code=502, content={"error": f"API a répondu {resp.status_code}"})

    return _format_commune(resp.json())


@app.get("/postal/{code_postal}")
async def get_by_postal(code_postal: str, request: Request):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if not code_postal.isdigit() or len(code_postal) not in (4, 5):
        return JSONResponse(status_code=422, content={"error": "Code postal invalide (ex: 75001)"})

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{GEO_API}/communes",
                params={"codePostal": code_postal, "fields": FIELDS, "limit": 50},
            )
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"API indisponible : {e}"})

    if resp.status_code != 200:
        return JSONResponse(status_code=502, content={"error": f"API a répondu {resp.status_code}"})

    communes = resp.json()
    return {
        "code_postal": code_postal,
        "count": len(communes),
        "communes": [_format_commune(c) for c in communes],
    }


@app.get("/search")
async def search(
    request: Request,
    q: str = Query(..., min_length=2, description="Nom de commune"),
    departement: Optional[str] = Query(default=None, description="Filtrer par code département (ex: 69)"),
    limit: int = Query(default=10, ge=1, le=50),
    boost_population: bool = Query(default=True),
):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    params: dict = {
        "nom": q,
        "fields": FIELDS,
        "limit": limit,
    }
    if departement:
        params["codeDepartement"] = departement
    if boost_population:
        params["boost"] = "population"

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{GEO_API}/communes", params=params)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"API indisponible : {e}"})

    if resp.status_code != 200:
        return JSONResponse(status_code=502, content={"error": f"API a répondu {resp.status_code}"})

    communes = resp.json()
    return {
        "query": q,
        "departement": departement,
        "count": len(communes),
        "communes": [_format_commune(c) for c in communes],
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-communes.suretat.com")
    return {"x402Version": 1, "accepts": [{
        "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"https://{host}/search",
        "description": "Données des communes françaises (INSEE, code postal, population...)",
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
    uvicorn.run(app, host="0.0.0.0", port=3092, proxy_headers=True, forwarded_allow_ips="*")
