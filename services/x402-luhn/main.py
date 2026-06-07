import os
import json
import re
import secrets
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field, AliasChoices

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
USDC_ADDRESS = os.getenv("USDC_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
NETWORK = os.getenv("NETWORK", "base")

app = FastAPI(title="x402 Luhn Validator", version="1.0.0")

PAYMENT_INFO = {
    "x402Version": 1,
    "accepts": [{
        "scheme": "exact",
        "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"http://{os.getenv('HOST', 'localhost')}:{os.getenv('PORT', '3066')}/validate",
        "description": "Luhn Validator / Credit Card Checker",
        "mimeType": "application/json",
        "payTo": PAY_TO,
        "maxTimeoutSeconds": 300,
        "asset": USDC_ADDRESS,
        "extra": {"name": "USD Coin", "version": "2"}
    }]
}

def verify_payment(request: Request) -> bool:
    return bool(request.headers.get("X-PAYMENT") or request.headers.get("x-payment", ""))

def luhn_check(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 2:
        return False
    total = 0
    reverse = digits[::-1]
    for i, d in enumerate(reverse):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0

def luhn_complete(partial: str) -> str:
    """Generate the check digit for a partial number."""
    digits = [int(d) for d in partial if d.isdigit()]
    digits.append(0)
    total = 0
    reverse = digits[::-1]
    for i, d in enumerate(reverse):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    check = (10 - (total % 10)) % 10
    return partial + str(check)

# Card type detection by IIN ranges
CARD_TYPES = [
    ("Visa", r"^4"),
    ("Mastercard", r"^5[1-5]|^2[2-7]"),
    ("American Express", r"^3[47]"),
    ("Discover", r"^6(?:011|5[0-9]{2})"),
    ("Diners Club", r"^3(?:0[0-5]|[68][0-9])"),
    ("JCB", r"^(?:2131|1800|35\d{3})"),
    ("UnionPay", r"^62"),
    ("Maestro", r"^(?:6304|6759|6761|6763)"),
    ("Carte Bancaire", r"^4[0-9]{15}$"),
]

def detect_card_type(number: str) -> str:
    for name, pattern in CARD_TYPES:
        if re.match(pattern, number):
            return name
    return "Inconnu"

class ValidateRequest(BaseModel):
    model_config = {"populate_by_name": True}
    numero: str = Field(
        validation_alias=AliasChoices('numero', 'number'),
        description="Numéro à valider (espaces/tirets acceptés)"
    )

class GenerateRequest(BaseModel):
    type_carte: str = Field(default="Visa", description="Type: Visa, Mastercard, AmEx")
    longueur: int = Field(default=16, ge=13, le=19)

class CompleteRequest(BaseModel):
    numero_partiel: str = Field(description="Numéro sans le dernier chiffre (chiffre de contrôle)")

@app.get("/")
def info():
    return {
        "service": "x402 Luhn Validator",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoints": ["POST /validate", "POST /generate", "POST /complete"],
        "docs": "/docs",
        "tagline": "Validate credit card numbers with Luhn algorithm — instant check",
        "curl_example": "curl https://x402-luhn.suretat.com/check -H 'Content-Type: application/json' -d '{\"number\": \"4532015112830366\"}'",
        "try_it": "https://x402-luhn.suretat.com/docs",
    }

@app.post("/validate")
async def validate(req: Request):
    if not verify_payment(req):
        return Response(content=json.dumps({"error": "Payment required", "x402": PAYMENT_INFO}),
                        status_code=402, media_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-ACCEPTS-PAYMENT": "x402"})
    try:
        raw = await req.json()
    except Exception:
        return Response(content=json.dumps({"error": "Invalid JSON"}), status_code=422, media_type="application/json")
    if 'number' in raw and 'numero' not in raw:
        raw['numero'] = raw.pop('number')
    try:
        body = ValidateRequest(**raw)
    except Exception as e:
        return Response(content=json.dumps({"error": str(e)}), status_code=422, media_type="application/json")
    clean = re.sub(r"[\s\-]", "", body.numero)
    if not clean.isdigit():
        return {"error": "Le numéro doit ne contenir que des chiffres, espaces ou tirets"}
    valid = luhn_check(clean)
    card_type = detect_card_type(clean)
    return {
        "numero_saisi": body.numero,
        "numero_normalise": clean,
        "longueur": len(clean),
        "luhn_valide": valid,
        "type_carte_detecte": card_type,
        "note": "Validation algorithmique uniquement — ne confirme pas l'existence du compte"
    }

@app.post("/generate")
async def generate(req: Request, body: GenerateRequest):
    if not verify_payment(req):
        return Response(content=json.dumps({"error": "Payment required", "x402": PAYMENT_INFO}),
                        status_code=402, media_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-ACCEPTS-PAYMENT": "x402"})
    # Generate a fake IIN prefix per card type
    prefixes = {
        "Visa": ["4"],
        "Mastercard": ["51", "52", "53", "54", "55"],
        "AmEx": ["34", "37"],
        "American Express": ["34", "37"],
        "Discover": ["6011"],
        "JCB": ["3528", "3589"],
    }
    card_type = body.type_carte
    prefix_list = prefixes.get(card_type, ["4"])
    prefix = secrets.choice(prefix_list)
    # Fill with random digits (leave room for check digit)
    remaining = body.longueur - len(prefix) - 1
    if remaining < 0:
        return {"error": f"Longueur {body.longueur} trop courte pour {card_type}"}
    partial = prefix + "".join(str(secrets.randbelow(10)) for _ in range(remaining))
    full = luhn_complete(partial)
    return {
        "numero": full,
        "type": card_type,
        "longueur": len(full),
        "luhn_valide": luhn_check(full),
        "avertissement": "Numéro fictif à usage de test uniquement"
    }

@app.post("/complete")
async def complete(req: Request, body: CompleteRequest):
    if not verify_payment(req):
        return Response(content=json.dumps({"error": "Payment required", "x402": PAYMENT_INFO}),
                        status_code=402, media_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-ACCEPTS-PAYMENT": "x402"})
    clean = re.sub(r"[\s\-]", "", body.numero_partiel)
    if not clean.isdigit():
        return {"error": "Chiffres uniquement"}
    completed = luhn_complete(clean)
    return {
        "numero_partiel": body.numero_partiel,
        "numero_complet": completed,
        "chiffre_controle": completed[-1],
        "luhn_valide": luhn_check(completed)
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
            "description": "x402 Luhn Validator",
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

