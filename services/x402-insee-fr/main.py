"""
x402 INSEE Statistiques FR — indicateurs économiques officiels par territoire
Sources: INSEE, geo.api.gouv.fr
Données: population, superficie, commune lookup, codes INSEE
Prix: 0.002 USDC/appel
"""
from __future__ import annotations
import os, re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

load_dotenv()

WALLET       = os.getenv("WALLET_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "2000")   # 0.002 USDC
FACILITATOR  = os.getenv("FACILITATOR_URL", "https://api.cdp.coinbase.com/platform/v2/x402")
USDC_BASE    = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
GEO_API      = "https://geo.api.gouv.fr"
INSEE_API    = "https://api.insee.fr/metadonnees/geo"

payments_total = 0
payments_log: list = []

PAYMENT_REQUIREMENTS = {
    "scheme": "exact",
    "network": "base",
    "maxAmountRequired": PRICE_ATOMIC,
    "resource": "https://x402-insee.suretat.com/commune",
    "description": "Données INSEE par commune: population, superficie, codes officiels",
    "mimeType": "application/json",
    "payTo": WALLET,
    "maxTimeoutSeconds": 300,
    "asset": USDC_BASE,
    "extra": {
        "name": "USD Coin",
        "version": "2",
        "bazaar": {
            "bodyType": "json",
            "input": {"commune": "Lyon"},
            "inputSchema": {
                "properties": {
                    "commune": {"type": "string", "description": "Nom ou code INSEE de la commune"},
                    "code_postal": {"type": "string", "description": "Code postal (optionnel)"},
                    "departement": {"type": "string", "description": "Numéro département (optionnel)"},
                },
            },
            "output": {
                "example": {
                    "nom": "Lyon",
                    "code": "69123",
                    "code_postal": ["69001","69002","69003"],
                    "departement": {"code": "69", "nom": "Rhône"},
                    "region": {"code": "84", "nom": "Auvergne-Rhône-Alpes"},
                    "population": 522228,
                    "superficie": 4787,
                    "centre": {"lat": 45.748, "lon": 4.847},
                }
            },
        },
    },
}


async def cdp_call(endpoint: str, payment_header: str) -> bool:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{FACILITATOR}/{endpoint}",
                json={
                    "x402Version": 1,
                    "paymentHeader": payment_header,
                    "paymentRequirements": [PAYMENT_REQUIREMENTS],
                },
            )
            if endpoint == "verify":
                return resp.json().get("isValid", False)
            return resp.status_code == 200
        except Exception:
            return False


async def get_commune_data(nom: str = None, code: str = None, code_postal: str = None, departement: str = None) -> dict:
    params: dict = {"fields": "nom,code,codesPostaux,departement,region,population,superficie,centre,contour", "limit": 5}
    if code:
        url = f"{GEO_API}/communes/{code}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params={"fields": "nom,code,codesPostaux,departement,region,population,superficie,centre"})
        if r.status_code != 200:
            return {"error": f"Commune non trouvée: {code}"}
        data = r.json()
        return _format_commune(data)
    elif code_postal:
        params["codePostal"] = code_postal
    elif nom:
        params["nom"] = nom
        if departement:
            params["codeDepartement"] = departement
    else:
        return {"error": "Paramètre requis: commune, code ou code_postal"}

    url = f"{GEO_API}/communes"
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, params=params)
    if r.status_code != 200:
        return {"error": f"Erreur API geo.gouv.fr: {r.status_code}"}
    communes = r.json()
    if not communes:
        return {"error": "Aucune commune trouvée"}
    if len(communes) == 1:
        return _format_commune(communes[0])
    # Return multiple results
    return {"resultats": [_format_commune(c) for c in communes[:5]], "total": len(communes)}


def _format_commune(c: dict) -> dict:
    result = {
        "nom": c.get("nom"),
        "code": c.get("code"),
        "codes_postaux": c.get("codesPostaux", []),
    }
    if dept := c.get("departement"):
        result["departement"] = {"code": dept.get("code"), "nom": dept.get("nom")}
    if reg := c.get("region"):
        result["region"] = {"code": reg.get("code"), "nom": reg.get("nom")}
    if pop := c.get("population"):
        result["population"] = pop
    if surf := c.get("superficie"):
        result["superficie_ha"] = surf
        result["superficie_km2"] = round(surf / 100, 2)
    if centre := c.get("centre"):
        coords = centre.get("coordinates", [])
        if len(coords) == 2:
            result["centre"] = {"lon": round(coords[0], 5), "lat": round(coords[1], 5)}
    return result


async def get_departement_data(code: str) -> dict:
    url = f"{GEO_API}/departements/{code}"
    params = {"fields": "nom,code,codeRegion,region"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, params=params)
    if r.status_code != 200:
        return {"error": f"Département non trouvé: {code}"}
    d = r.json()
    result = {
        "nom": d.get("nom"),
        "code": d.get("code"),
    }
    if reg := d.get("region"):
        result["region"] = {"code": reg.get("code"), "nom": reg.get("nom")}
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[x402-insee] Wallet: {WALLET}")
    yield


app = FastAPI(title="x402 INSEE Statistiques FR", version="1.0.0", lifespan=lifespan)


class CommuneRequest(BaseModel):
    commune: Optional[str] = None
    code: Optional[str] = None
    code_postal: Optional[str] = None
    departement: Optional[str] = None


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    protected = ("/commune", "/departement", "/region")
    if not any(request.url.path.startswith(p) for p in protected):
        return await call_next(request)
    payment_header = request.headers.get("X-PAYMENT")
    if not payment_header:
        return JSONResponse(
            status_code=402,
            content={"x402Version": 1, "accepts": [PAYMENT_REQUIREMENTS], "error": "Payment required"},
                    headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
        )
    if not await cdp_call("verify", payment_header):
        return JSONResponse(
            status_code=402,
            content={"x402Version": 1, "error": "Paiement invalide ou expiré"},
                    headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
        )
    response = await call_next(request)
    await cdp_call("settle", payment_header)
    global payments_total, payments_log
    payments_total += 1
    payments_log.append({"n": payments_total, "at": datetime.now(timezone.utc).isoformat()})
    if len(payments_log) > 100:
        payments_log = payments_log[-100:]
    print(f"[x402-insee] PAIEMENT #{payments_total}")
    return response


@app.get("/")
async def root():
    return {
        "service": "x402 INSEE Statistiques FR",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.002 USDC/appel",
        "endpoints": {
            "POST /commune": "Données commune par nom/code/code postal",
            "POST /departement": "Données département par code (01, 75, 69...)",
        },
        "source": "geo.api.gouv.fr (officiel)",
        "docs": "/docs",
        "tagline": "INSEE code lookup — commune, department, region info from code",
        "curl_example": "curl https://x402-insee-fr.suretat.com/lookup -H 'Content-Type: application/json' -d '{\"code\": \"75056\"}'",
        "try_it": "https://x402-insee-fr.suretat.com/docs",
    }


@app.post("/commune")
async def commune_lookup(payload: CommuneRequest):
    if not any([payload.commune, payload.code, payload.code_postal]):
        return JSONResponse(status_code=400, content={"error": "Paramètre requis: commune, code ou code_postal"})
    result = await get_commune_data(
        nom=payload.commune,
        code=payload.code,
        code_postal=payload.code_postal,
        departement=payload.departement,
    )
    if "error" in result:
        return JSONResponse(status_code=404 if "trouvé" in result["error"] else 502, content=result)
    return result


@app.post("/departement")
async def departement_lookup(payload: dict):
    code = str(payload.get("code", "")).strip()
    if not code:
        return JSONResponse(status_code=400, content={"error": "Champ 'code' requis (01, 75, 69, 2A...)"})
    result = await get_departement_data(code)
    if "error" in result:
        return JSONResponse(status_code=404 if "trouvé" in result["error"] else 502, content=result)
    return result


@app.get("/stats")
async def stats():
    return {"service": "x402-insee-fr", "payments_total": payments_total, "last_payments": payments_log[-10:]}

@app.get("/.well-known/x402.json")
async def x402_well_known():
    return {"x402Version": 1, "accepts": [PAYMENT_REQUIREMENTS]}

@app.get("/.well-known/x402")
async def x402_well_known_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/.well-known/x402.json")

