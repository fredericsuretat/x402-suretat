from __future__ import annotations
import logging
import os
import time
from datetime import datetime
from typing import Any

import uvicorn
from croniter import croniter
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-cron")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

COMMON_CRON = {
    "* * * * *":      "Toutes les minutes",
    "*/5 * * * *":    "Toutes les 5 minutes",
    "0 * * * *":      "Toutes les heures",
    "0 9 * * *":      "Chaque jour à 9h",
    "0 9 * * 1":      "Chaque lundi à 9h",
    "0 0 * * *":      "Minuit chaque nuit",
    "0 0 1 * *":      "Le 1er du mois à minuit",
    "0 0 1 1 *":      "Le 1er janvier",
    "*/30 9-18 * * 1-5": "Toutes les 30 min, 9h-18h, lun-ven",
    "0 9,12,18 * * *": "3 fois par jour (9h, 12h, 18h)",
}

app = FastAPI(title="x402 Cron Parser", version="1.0.0")


class CronRequest(BaseModel):
    expression: str = Field(..., description="Expression cron (ex: '0 9 * * 1-5')", examples=["0 9 * * 1-5"])
    count: int = Field(default=5, ge=1, le=20, description="Nombre de prochaines exécutions")
    from_datetime: str | None = Field(default=None, description="Date de départ ISO 8601 (défaut: maintenant)")


@app.get("/")
def root():
    return {
        "service": "x402 Cron Parser",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/analyse",
        "endpoint": "POST /parse",
        "fonctionnalites": ["validation expression", "prochaines exécutions", "description humaine", "expressions courantes"],
        "docs": "/docs",
        "tagline": "Parse and explain cron expressions in plain English or French",
        "curl_example": "curl https://x402-cron.suretat.com/explain -H 'Content-Type: application/json' -d '{\"expression\": \"0 9 * * 1-5\", \"lang\": \"fr\"}'",
        "try_it": "https://x402-cron.suretat.com/docs",
    }


@app.get("/examples")
def get_examples():
    return {"expressions_courantes": COMMON_CRON}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/parse" and request.method == "POST":
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
                        "description": "Cron expression parsing — 0.0005 USDC",
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


def _describe_cron(expr: str) -> str:
    parts = expr.strip().split()
    if len(parts) != 5:
        return "Expression non standard"
    m, h, dom, mon, dow = parts

    dow_map = {"0": "dim", "1": "lun", "2": "mar", "3": "mer", "4": "jeu", "5": "ven", "6": "sam",
               "7": "dim", "MON": "lun", "TUE": "mar", "WED": "mer", "THU": "jeu",
               "FRI": "ven", "SAT": "sam", "SUN": "dim"}

    if expr in COMMON_CRON:
        return COMMON_CRON[expr]

    desc = []
    if m == "*" and h == "*":
        desc.append("Toutes les minutes")
    elif m.startswith("*/"):
        desc.append(f"Toutes les {m[2:]} minutes")
    else:
        desc.append(f"À {h}h{m.zfill(2)}")

    if dom != "*":
        desc.append(f"le {dom} du mois")
    if mon != "*":
        desc.append(f"en mois {mon}")
    if dow != "*":
        desc.append(f"les jours {dow}")

    return " ".join(desc) if desc else expr


@app.post("/parse")
def parse_cron(req: CronRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    expr = req.expression.strip()

    if not croniter.is_valid(expr):
        return JSONResponse(status_code=400, content={
            "valide": False,
            "expression": expr,
            "erreur": "Expression cron invalide",
            "exemples": list(COMMON_CRON.keys())[:5],
        })

    if req.from_datetime:
        try:
            base_dt = datetime.fromisoformat(req.from_datetime)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": f"Date invalide: {e}"})
    else:
        base_dt = datetime.now()

    cron = croniter(expr, base_dt)
    next_runs = []
    for _ in range(req.count):
        dt = cron.get_next(datetime)
        seconds_from_now = int((dt - datetime.now()).total_seconds())
        next_runs.append({
            "datetime": dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "display": dt.strftime("%d/%m/%Y %H:%M"),
            "dans": f"dans {seconds_from_now // 3600}h{(seconds_from_now % 3600) // 60}m" if seconds_from_now > 0 else "passé",
        })

    return {
        "expression": expr,
        "valide": True,
        "description": _describe_cron(expr),
        "prochaines_executions": next_runs,
        "champs": {
            "minutes": expr.split()[0],
            "heures": expr.split()[1],
            "jour_mois": expr.split()[2],
            "mois": expr.split()[3],
            "jour_semaine": expr.split()[4],
        },
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
            "resource": f"https://{host}/parse",
            "description": "x402 Cron Parser",
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
    uvicorn.run(app, host="0.0.0.0", port=3057)
