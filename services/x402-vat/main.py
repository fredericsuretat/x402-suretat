from __future__ import annotations
import logging
import os
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-vat-fr")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

# French VAT rates (taux TVA France)
TVA_RATES = {
    "normal": {"taux": "20", "description": "Taux normal (biens et services courants)"},
    "intermediaire": {"taux": "10", "description": "Taux intermédiaire (restaurant, transport, hôtel, rénovation)"},
    "reduit": {"taux": "5.5", "description": "Taux réduit (alimentation, livres, médicaments, billetterie culturelle)"},
    "super_reduit": {"taux": "2.1", "description": "Taux super-réduit (médicaments remboursables, presse)"},
}

app = FastAPI(title="x402 VAT Calculator FR", version="1.0.0")


class VATRequest(BaseModel):
    montant: float = Field(..., description="Montant en euros", gt=0)
    type_montant: Literal["ht", "ttc"] = Field(default="ht", description="Type: ht (HT = hors taxes) ou ttc (TTC = toutes taxes comprises)")
    taux_tva: str = Field(default="normal", description="Taux: normal (20%), intermediaire (10%), reduit (5.5%), super_reduit (2.1%), ou valeur numérique (ex: '8.5')")
    arrondi: int = Field(default=2, ge=0, le=6, description="Décimales pour l'arrondi")


class InvoiceRequest(BaseModel):
    lignes: list[dict] = Field(..., description="Lignes de facture: [{'description': '...', 'montant_ht': ..., 'taux_tva': 'normal', 'quantite': 1}]")
    devise: str = Field(default="EUR", description="Code devise")


@app.get("/")
def root():
    return {
        "service": "x402 VAT Calculator FR",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/calcul",
        "endpoints": {
            "POST /calculate": "Calculer TVA sur un montant",
            "POST /invoice": "Calculer TVA sur plusieurs lignes de facture",
            "GET /rates": "Liste des taux TVA français",
        },
        "tagline": "Calculate French VAT (TVA) for any amount — HT/TTC, all rates, invoice support",
        "curl_example": "curl https://x402-vat-fr.suretat.com/calculate -H 'Content-Type: application/json' -d '{\"montant\": 100, \"type_montant\": \"ht\", \"taux_tva\": \"normal\"}'",
        "try_it": "https://x402-vat-fr.suretat.com/docs",
        "docs": "/docs",
    }


@app.get("/rates")
def get_rates():
    return {"taux_tva_france": TVA_RATES}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path in ("/calculate", "/invoice") and request.method == "POST":
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
                        "description": "TVA calculation — 0.0005 USDC",
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


def _resolve_rate(taux_str: str) -> Decimal:
    if taux_str in TVA_RATES:
        return Decimal(TVA_RATES[taux_str]["taux"])
    try:
        return Decimal(str(taux_str))
    except Exception:
        raise ValueError(f"Taux inconnu: {taux_str}")


def _format(d: Decimal, decimals: int) -> float:
    quantize_str = "0." + "0" * decimals if decimals > 0 else "0"
    return float(d.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP))


@app.post("/calculate")
def calculate_vat(req: VATRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        taux = _resolve_rate(req.taux_tva)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e), "taux_disponibles": list(TVA_RATES.keys())})

    montant = Decimal(str(req.montant))
    taux_decimal = taux / Decimal("100")

    if req.type_montant == "ht":
        ht = montant
        tva = ht * taux_decimal
        ttc = ht + tva
    else:  # ttc
        ttc = montant
        ht = ttc / (1 + taux_decimal)
        tva = ttc - ht

    dec = req.arrondi
    taux_info = TVA_RATES.get(req.taux_tva, {"description": f"Taux {taux}%"})

    return {
        "montant_ht": _format(ht, dec),
        "montant_tva": _format(tva, dec),
        "montant_ttc": _format(ttc, dec),
        "taux_tva_pct": float(taux),
        "taux_nom": req.taux_tva if req.taux_tva in TVA_RATES else "personnalisé",
        "description_taux": taux_info.get("description", ""),
        "devise": "EUR",
    }


@app.post("/invoice")
def calculate_invoice(req: InvoiceRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    total_ht = Decimal("0")
    total_tva = Decimal("0")
    lignes_result = []
    tva_par_taux: dict[str, Decimal] = {}

    for i, ligne in enumerate(req.lignes):
        desc = ligne.get("description", f"Ligne {i+1}")
        montant_ht_unit = Decimal(str(ligne.get("montant_ht", 0)))
        qty = Decimal(str(ligne.get("quantite", 1)))
        taux_str = str(ligne.get("taux_tva", "normal"))

        try:
            taux = _resolve_rate(taux_str)
        except ValueError:
            taux = Decimal("20")
            taux_str = "normal"

        ht = montant_ht_unit * qty
        tva_line = ht * (taux / Decimal("100"))
        ttc_line = ht + tva_line

        total_ht += ht
        total_tva += tva_line
        tva_par_taux[str(taux)] = tva_par_taux.get(str(taux), Decimal("0")) + tva_line

        lignes_result.append({
            "description": desc,
            "quantite": float(qty),
            "prix_unitaire_ht": float(montant_ht_unit),
            "montant_ht": _format(ht, 2),
            "taux_tva_pct": float(taux),
            "montant_tva": _format(tva_line, 2),
            "montant_ttc": _format(ttc_line, 2),
        })

    total_ttc = total_ht + total_tva
    return {
        "lignes": lignes_result,
        "total_ht": _format(total_ht, 2),
        "total_tva": _format(total_tva, 2),
        "total_ttc": _format(total_ttc, 2),
        "tva_par_taux": {f"{k}%": _format(v, 2) for k, v in sorted(tva_par_taux.items(), key=lambda x: -float(x[0]))},
        "devise": req.devise,
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
            "description": "x402 VAT Calculator FR",
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
    uvicorn.run(app, host="0.0.0.0", port=3061)
