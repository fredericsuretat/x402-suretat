import os
import json
from datetime import date, timedelta
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field

FACILITATOR_URL = os.getenv("FACILITATOR_URL", "https://api.cdp.coinbase.com/platform/v2/x402")
PAY_TO = os.getenv("PAY_TO_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
USDC_ADDRESS = os.getenv("USDC_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
NETWORK = os.getenv("NETWORK", "base")

app = FastAPI(title="x402 Jours Fériés FR", version="1.0.0")

PAYMENT_INFO = {
    "x402Version": 1,
    "accepts": [{
        "scheme": "exact",
        "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"http://{os.getenv('HOST', 'localhost')}:{os.getenv('PORT', '3063')}/feries",
        "description": "Jours Fériés France",
        "mimeType": "application/json",
        "payTo": PAY_TO,
        "maxTimeoutSeconds": 300,
        "asset": USDC_ADDRESS,
        "extra": {"name": "USD Coin", "version": "2"}
    }]
}

def verify_payment(request: Request) -> bool:
    token = request.headers.get("X-PAYMENT") or request.headers.get("x-payment", "")
    return bool(token)

# Easter using the Anonymous Gregorian algorithm
def easter(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)

ZONES = {
    "metropole": "France métropolitaine",
    "alsace-moselle": "Alsace-Moselle",
    "guadeloupe": "Guadeloupe",
    "martinique": "Martinique",
    "guyane": "Guyane",
    "la-reunion": "La Réunion",
    "mayotte": "Mayotte",
    "saint-barthelemy": "Saint-Barthélemy",
    "saint-martin": "Saint-Martin",
    "saint-pierre-et-miquelon": "Saint-Pierre-et-Miquelon",
    "nouvelle-caledonie": "Nouvelle-Calédonie",
    "polynesie-francaise": "Polynésie Française",
    "wallis-et-futuna": "Wallis-et-Futuna",
}

def compute_feries(year: int, zone: str = "metropole") -> dict:
    p = easter(year)
    feries = {}

    # Universal French public holidays
    feries[f"{year}-01-01"] = "Jour de l'An"
    feries[(p + timedelta(days=1)).isoformat()] = "Lundi de Pâques"
    feries[f"{year}-05-01"] = "Fête du Travail"
    feries[f"{year}-05-08"] = "Victoire 1945"
    feries[(p + timedelta(days=39)).isoformat()] = "Ascension"
    feries[(p + timedelta(days=50)).isoformat()] = "Lundi de Pentecôte"
    feries[f"{year}-07-14"] = "Fête Nationale"
    feries[f"{year}-08-15"] = "Assomption"
    feries[f"{year}-11-01"] = "Toussaint"
    feries[f"{year}-11-11"] = "Armistice"
    feries[f"{year}-12-25"] = "Noël"

    # Alsace-Moselle extra holidays
    if zone in ("alsace-moselle",):
        feries[(p - timedelta(days=2)).isoformat()] = "Vendredi Saint"
        feries[f"{year}-12-26"] = "Saint Étienne (2ème jour de Noël)"

    # DOM-TOM specifics
    if zone in ("guadeloupe", "martinique"):
        feries[f"{year}-05-22"] = "Abolition de l'esclavage (Martinique/Guadeloupe)"
    if zone == "guyane":
        feries[f"{year}-06-10"] = "Abolition de l'esclavage (Guyane)"
    if zone == "la-reunion":
        feries[f"{year}-12-20"] = "Abolition de l'esclavage (Réunion)"
    if zone == "mayotte":
        feries[f"{year}-04-27"] = "Abolition de l'esclavage (Mayotte)"

    return dict(sorted(feries.items()))

def is_working_day(d: date, zone: str = "metropole") -> bool:
    if d.weekday() >= 5:
        return False
    feries = compute_feries(d.year, zone)
    return d.isoformat() not in feries

def count_working_days(start: date, end: date, zone: str = "metropole") -> int:
    count = 0
    d = start
    while d <= end:
        if is_working_day(d, zone):
            count += 1
        d += timedelta(days=1)
    return count

class FeriesRequest(BaseModel):
    annee: int = Field(default=2026, ge=1900, le=2100)
    zone: str = Field(default="metropole")

class WorkingDaysRequest(BaseModel):
    debut: str = Field(description="Date de début YYYY-MM-DD")
    fin: str = Field(description="Date de fin YYYY-MM-DD")
    zone: str = Field(default="metropole")

@app.get("/")
def info():
    return {
        "service": "x402 Jours Fériés FR",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoints": ["POST /feries", "POST /jours-ouvres"],
        "zones": list(ZONES.keys()),
        "docs": "/docs",
        "tagline": "Get French public holidays and working days for any year and zone",
        "curl_example": "curl https://x402-feries.suretat.com/feries -H 'Content-Type: application/json' -d '{\"annee\": 2024, \"zone\": \"metropole\"}'",
        "try_it": "https://x402-feries.suretat.com/docs",
    }

@app.post("/feries")
async def feries(req: Request, body: FeriesRequest):
    if not verify_payment(req):
        return Response(
            content=json.dumps({"error": "Payment required", "x402": PAYMENT_INFO}),
            status_code=402,
            media_type="application/json",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-ACCEPTS-PAYMENT": "x402"}
        )
    zone = body.zone.lower()
    if zone not in ZONES:
        zone = "metropole"
    jours = compute_feries(body.annee, zone)
    return {
        "annee": body.annee,
        "zone": zone,
        "zone_nom": ZONES[zone],
        "nombre": len(jours),
        "jours_feries": [{"date": k, "nom": v} for k, v in jours.items()]
    }

@app.post("/jours-ouvres")
async def jours_ouvres(req: Request, body: WorkingDaysRequest):
    if not verify_payment(req):
        return Response(
            content=json.dumps({"error": "Payment required", "x402": PAYMENT_INFO}),
            status_code=402,
            media_type="application/json",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-ACCEPTS-PAYMENT": "x402"}
        )
    try:
        start = date.fromisoformat(body.debut)
        end = date.fromisoformat(body.fin)
    except ValueError as e:
        return {"error": f"Format de date invalide: {e}"}
    if start > end:
        return {"error": "debut doit être avant fin"}
    if (end - start).days > 366:
        return {"error": "Plage maximale: 366 jours"}
    zone = body.zone.lower()
    if zone not in ZONES:
        zone = "metropole"
    count = count_working_days(start, end, zone)
    total_jours = (end - start).days + 1
    return {
        "debut": body.debut,
        "fin": body.fin,
        "zone": zone,
        "total_jours_calendaires": total_jours,
        "jours_ouvres": count,
        "jours_non_ouvres": total_jours - count
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
            "description": "x402 Jours Fériés FR",
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

