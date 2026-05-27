from __future__ import annotations
import logging
import os
import re
import secrets
import string
import time
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from zxcvbn import zxcvbn

log = logging.getLogger("x402-password")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Password Tools", version="1.0.0")

STRENGTH_LABELS = ["Très faible", "Faible", "Moyen", "Fort", "Très fort"]


class GenerateRequest(BaseModel):
    length: int = Field(default=20, ge=8, le=128, description="Longueur du mot de passe")
    uppercase: bool = Field(default=True)
    lowercase: bool = Field(default=True)
    digits: bool = Field(default=True)
    special: bool = Field(default=True)
    exclude_ambiguous: bool = Field(default=False, description="Exclure 0, O, 1, l, I")
    count: int = Field(default=1, ge=1, le=10, description="Nombre de mots de passe à générer")
    mode: Literal["random", "passphrase"] = Field(default="random", description="random = aléatoire, passphrase = suite de mots")


class CheckRequest(BaseModel):
    password: str = Field(..., description="Mot de passe à analyser", max_length=1000)
    user_inputs: list[str] = Field(default=[], description="Données contextuelles à éviter (nom, email, etc.)")


def _generate_one(req: GenerateRequest) -> str:
    alphabet = ""
    if req.uppercase:
        alphabet += string.ascii_uppercase
    if req.lowercase:
        alphabet += string.ascii_lowercase
    if req.digits:
        alphabet += string.digits
    if req.special:
        alphabet += "!@#$%^&*()-_=+[]{}|;:,.<>?"

    if req.exclude_ambiguous:
        for ch in "0O1lI":
            alphabet = alphabet.replace(ch, "")

    if not alphabet:
        alphabet = string.ascii_letters + string.digits

    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(req.length))
        if req.uppercase and not any(c.isupper() for c in pwd):
            continue
        if req.lowercase and not any(c.islower() for c in pwd):
            continue
        if req.digits and not any(c.isdigit() for c in pwd):
            continue
        if req.special and not any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in pwd):
            continue
        return pwd


WORDLIST = [
    "soleil", "montagne", "rivière", "château", "jardin", "fenêtre", "lumière",
    "musique", "voyage", "librairie", "chocolat", "aventure", "papillon", "horizon",
    "forêt", "cascade", "étoile", "chemin", "silence", "tempête", "aurore",
    "colline", "nuage", "plage", "fontaine", "balcon", "cerisier", "crépuscule",
    "cristal", "mystère", "vague", "prairie", "ruisseau", "brouillard", "saphir",
]


@app.get("/")
def root():
    return {
        "service": "x402 Password Tools",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/appel",
        "endpoints": {"POST /generate": "Génère des mots de passe sécurisés", "POST /check": "Analyse la force d'un mot de passe"},
        "docs": "/docs",
        "tagline": "Generate secure passwords with custom rules — entropy score included",
        "curl_example": "curl https://x402-password.suretat.com/generate -H 'Content-Type: application/json' -d '{\"length\": 16, \"symbols\": true, \"digits\": true}'",
        "try_it": "https://x402-password.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path in ("/generate", "/check") and request.method == "POST":
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
                        "description": "Password tools — 0.0005 USDC",
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


@app.post("/generate")
def generate_password(req: GenerateRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if req.mode == "passphrase":
        passwords = []
        for _ in range(req.count):
            words = [secrets.choice(WORDLIST) for _ in range(4)]
            sep = secrets.choice(["-", "_", ".", "!"])
            num = secrets.randbelow(100)
            pwd = sep.join(words) + str(num)
            passwords.append(pwd)
    else:
        passwords = [_generate_one(req) for _ in range(req.count)]

    results = []
    for pwd in passwords:
        z = zxcvbn(pwd)
        results.append({
            "password": pwd,
            "longueur": len(pwd),
            "force_score": z["score"],
            "force_label": STRENGTH_LABELS[z["score"]],
            "crack_time": z["crack_times_display"]["offline_slow_hashing_1e4_per_second"],
        })

    return {"passwords": results[0] if req.count == 1 else results}


@app.post("/check")
def check_password(req: CheckRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    z = zxcvbn(req.password, user_inputs=req.user_inputs)

    warnings = []
    if z["feedback"]["warning"]:
        warnings.append(z["feedback"]["warning"])
    suggestions = z["feedback"]["suggestions"]

    return {
        "longueur": len(req.password),
        "force_score": z["score"],
        "force_label": STRENGTH_LABELS[z["score"]],
        "entropie_estimee": z.get("guesses_log10", 0),
        "temps_crack": {
            "online_throttle": z["crack_times_display"]["online_throttling_100_per_hour"],
            "online_no_throttle": z["crack_times_display"]["online_no_throttling_10_per_second"],
            "offline_slow": z["crack_times_display"]["offline_slow_hashing_1e4_per_second"],
            "offline_fast": z["crack_times_display"]["offline_fast_hashing_1e10_per_second"],
        },
        "avertissements": warnings,
        "suggestions": suggestions,
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
            "description": "x402 Password Tools",
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
    uvicorn.run(app, host="0.0.0.0", port=3052)
