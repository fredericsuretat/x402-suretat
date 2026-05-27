from __future__ import annotations
import logging
import os
import re
import time
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-regex")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

COMMON_REGEX = {
    "email": r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$",
    "url": r"https?://[^\s/$.?#].[^\s]*",
    "ipv4": r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$",
    "ipv6": r"^([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}$",
    "date_fr": r"^(0?[1-9]|[12]\d|3[01])/(0?[1-9]|1[012])/(19|20)\d\d$",
    "date_iso": r"^\d{4}-(?:0[1-9]|1[012])-(?:0[1-9]|[12]\d|3[01])$",
    "phone_fr": r"^(?:\+33|0033|0)[1-9](?:[\s.-]?\d{2}){4}$",
    "siret": r"^\d{3}[\s]?\d{3}[\s]?\d{3}[\s]?\d{5}$",
    "code_postal_fr": r"^(?:0[1-9]|[1-8]\d|9[0-5])\d{3}$",
    "immatriculation_fr": r"^[A-Z]{2}-\d{3}-[A-Z]{2}$",
    "hex_color": r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$",
    "slug": r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    "isbn13": r"^97[89]\d{10}$",
    "credit_card": r"^(?:4\d{12}(?:\d{3})?|5[1-5]\d{14}|3[47]\d{13}|6(?:011|5\d{2})\d{12})$",
}

app = FastAPI(title="x402 Regex Tester", version="1.0.0")


class RegexRequest(BaseModel):
    pattern: str = Field(..., description="Expression régulière Python")
    text: str = Field(..., description="Texte à tester", max_length=100_000)
    flags: list[str] = Field(default=[], description="Flags: IGNORECASE, MULTILINE, DOTALL, UNICODE")
    operation: Literal["match", "search", "findall", "split", "sub"] = Field(
        default="search",
        description="match: ancré au début, search: n'importe où, findall: toutes occurrences, split: découpage, sub: substitution"
    )
    replacement: str | None = Field(default=None, description="Texte de remplacement (pour operation=sub)")
    max_results: int = Field(default=20, ge=1, le=100, description="Nombre max de résultats (findall)")


@app.get("/")
def root():
    return {
        "service": "x402 Regex Tester",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/test",
        "endpoint": "POST /test",
        "operations": ["match", "search", "findall", "split", "sub"],
        "regex_communs": list(COMMON_REGEX.keys()),
        "docs": "/docs",
        "tagline": "Test regex patterns against text — returns all matches with groups",
        "curl_example": "curl https://x402-regex.suretat.com/test -H 'Content-Type: application/json' -d '{\"pattern\": \"\\d{4}\", \"text\": \"Year 2024 and 2025\"}'",
        "try_it": "https://x402-regex.suretat.com/docs",
    }


@app.get("/patterns")
def get_patterns():
    return {"patterns_courants": COMMON_REGEX}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/test" and request.method == "POST":
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
                        "description": "Regex testing — 0.0005 USDC",
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


@app.post("/test")
def test_regex(req: RegexRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    # Check for known alias
    pattern = COMMON_REGEX.get(req.pattern, req.pattern)

    # Compile flags
    flag_map = {
        "IGNORECASE": re.IGNORECASE, "I": re.IGNORECASE,
        "MULTILINE": re.MULTILINE, "M": re.MULTILINE,
        "DOTALL": re.DOTALL, "S": re.DOTALL,
        "UNICODE": re.UNICODE, "U": re.UNICODE,
    }
    flags = 0
    for f in req.flags:
        flags |= flag_map.get(f.upper(), 0)

    try:
        compiled = re.compile(pattern, flags)
    except re.error as e:
        return JSONResponse(status_code=400, content={
            "valide": False,
            "pattern": pattern,
            "erreur": str(e),
            "patterns_courants": list(COMMON_REGEX.keys()),
        })

    result: dict = {"pattern": pattern, "valide": True, "operation": req.operation}

    if req.operation == "match":
        m = compiled.match(req.text)
        result["correspond"] = bool(m)
        if m:
            result["match"] = m.group()
            result["groupes"] = list(m.groups())
            result["position"] = {"debut": m.start(), "fin": m.end()}

    elif req.operation == "search":
        m = compiled.search(req.text)
        result["trouve"] = bool(m)
        if m:
            result["match"] = m.group()
            result["groupes"] = list(m.groups())
            result["position"] = {"debut": m.start(), "fin": m.end()}

    elif req.operation == "findall":
        matches = compiled.findall(req.text)[:req.max_results]
        result["nb_correspondances"] = len(matches)
        result["correspondances"] = matches
        result["tronque"] = len(compiled.findall(req.text)) > req.max_results

    elif req.operation == "split":
        parts = compiled.split(req.text, maxsplit=req.max_results)
        result["parties"] = parts
        result["nb_parties"] = len(parts)

    elif req.operation == "sub":
        if req.replacement is None:
            return JSONResponse(status_code=400, content={"error": "replacement est requis pour l'opération 'sub'"})
        new_text, count = compiled.subn(req.replacement, req.text)
        result["texte_modifie"] = new_text
        result["nb_substitutions"] = count

    return result



@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK if "NETWORK" in dir() else os.getenv("NETWORK", "base"),
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/test",
            "description": "x402 Regex Tester",
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
    uvicorn.run(app, host="0.0.0.0", port=3059)
