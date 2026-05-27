from __future__ import annotations
import json
import logging
import os
import time
from typing import Any

import jsonschema
from jsonschema import Draft7Validator, Draft202012Validator, validate
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-jsonschema")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 JSON Schema Validator", version="1.0.0")


class ValidateRequest(BaseModel):
    data: Any = Field(..., description="Données JSON à valider")
    schema_: Any = Field(..., alias="schema", description="JSON Schema de validation")
    draft: str = Field(default="draft7", description="Version: draft7, draft202012")
    collect_all_errors: bool = Field(default=True, description="Collecter toutes les erreurs (vs arrêter au premier)")


class FormatRequest(BaseModel):
    json_str: str = Field(..., description="Chaîne JSON à formater", max_length=500_000)
    indent: int = Field(default=2, ge=0, le=8)
    sort_keys: bool = Field(default=False)


@app.get("/")
def root():
    return {
        "service": "x402 JSON Schema Validator",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/validation",
        "endpoints": {
            "POST /validate": "Valider JSON contre un schema",
            "POST /format": "Formater et minifier du JSON",
        },
        "drafts": ["draft7", "draft202012"],
        "docs": "/docs",
        "tagline": "Validate JSON data against a JSON Schema — returns detailed errors",
        "curl_example": "curl https://x402-jsonschema.suretat.com/validate -H 'Content-Type: application/json' -d '{\"schema\": {\"type\": \"object\", \"required\": [\"name\"]}, \"data\": {\"name\": \"Alice\"}}'",
        "try_it": "https://x402-jsonschema.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path in ("/validate", "/format") and request.method == "POST":
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
                        "description": "JSON validation — 0.0005 USDC",
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
def validate_json(req: ValidateRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    ValidatorClass = Draft202012Validator if req.draft == "draft202012" else Draft7Validator

    try:
        validator = ValidatorClass(req.schema_)
        meta_errors = list(validator.iter_errors(req.schema_))
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Schema invalide: {e}"})

    if req.collect_all_errors:
        errors = list(validator.iter_errors(req.data))
    else:
        errors = []
        try:
            validator.validate(req.data)
        except jsonschema.ValidationError as e:
            errors = [e]

    if not errors:
        return {"valide": True, "erreurs": [], "nb_erreurs": 0, "draft": req.draft}

    return {
        "valide": False,
        "nb_erreurs": len(errors),
        "draft": req.draft,
        "erreurs": [
            {
                "message": e.message,
                "chemin": ".".join(str(p) for p in e.absolute_path) or "(racine)",
                "schema_chemin": ".".join(str(p) for p in e.absolute_schema_path),
                "valeur_invalide": str(e.instance)[:200],
                "validateur": e.validator,
            }
            for e in errors
        ],
    }


@app.post("/format")
def format_json(req: FormatRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        parsed = json.loads(req.json_str)
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=400, content={"error": f"JSON invalide: {e}"})

    formatted = json.dumps(parsed, indent=req.indent, sort_keys=req.sort_keys, ensure_ascii=False)
    minified = json.dumps(parsed, separators=(",", ":"), sort_keys=req.sort_keys, ensure_ascii=False)

    return {
        "valide": True,
        "formatted": formatted,
        "minified": minified,
        "taille_originale": len(req.json_str),
        "taille_formatee": len(formatted),
        "taille_minifiee": len(minified),
        "compression": f"{round((1 - len(minified)/len(req.json_str)) * 100, 1)}%",
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
            "description": "x402 JSON Schema Validator",
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
    uvicorn.run(app, host="0.0.0.0", port=3054)
