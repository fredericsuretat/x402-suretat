from __future__ import annotations
import logging
import os
import time
from typing import Literal

import uvicorn
from faker import Faker
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-fakedata")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

fake_fr = Faker("fr_FR")
fake_en = Faker("en_US")

PROFILES = {
    "personne": ["nom_complet", "prenom", "nom", "email", "telephone", "date_naissance", "genre", "adresse", "ville", "code_postal", "departement"],
    "entreprise": ["nom_entreprise", "siret_fake", "siren_fake", "adresse", "ville", "code_postal", "telephone", "email_pro", "secteur", "site_web"],
    "adresse": ["rue", "ville", "code_postal", "departement", "region", "pays"],
    "paiement": ["iban_fake", "bic_fake", "numero_carte", "date_expiration_carte"],
    "internet": ["email", "username", "password_fake", "user_agent", "ipv4", "ipv6", "url", "domaine"],
    "texte": ["titre", "paragraphe", "phrase", "mots"],
    "tout": None,
}

app = FastAPI(title="x402 Fake Data FR", version="1.0.0")


class FakeDataRequest(BaseModel):
    profil: str = Field(default="personne", description=f"Profil à générer: {', '.join(PROFILES.keys())}")
    count: int = Field(default=1, ge=1, le=20, description="Nombre d'enregistrements (max 20)")
    seed: int | None = Field(default=None, description="Graine pour résultats reproductibles")


def _make_siret():
    siren = "".join([str(fake_fr.random_digit()) for _ in range(9)])
    nic = "".join([str(fake_fr.random_digit()) for _ in range(5)])
    return f"{siren[:3]} {siren[3:6]} {siren[6:]} {nic}"


def _make_iban():
    bban = "".join([str(fake_fr.random_digit()) for _ in range(23)])
    return f"FR76 {bban[:4]} {bban[4:8]} {bban[8:12]} {bban[12:16]} {bban[16:20]} {bban[20:]}"


def generate_record(profil: str) -> dict:
    f = fake_fr
    data = {}

    fields = PROFILES.get(profil)
    if fields is None:
        fields = [f for p in PROFILES.values() if p for f in p]

    for field in fields:
        if field == "nom_complet":       data[field] = f.name()
        elif field == "prenom":          data[field] = f.first_name()
        elif field == "nom":             data[field] = f.last_name()
        elif field == "email":           data[field] = f.email()
        elif field == "telephone":       data[field] = f.phone_number()
        elif field == "date_naissance":  data[field] = str(f.date_of_birth(minimum_age=18, maximum_age=80))
        elif field == "genre":           data[field] = f.random_element(["M", "F"])
        elif field == "adresse":         data[field] = f.street_address()
        elif field == "rue":             data[field] = f.street_address()
        elif field == "ville":           data[field] = f.city()
        elif field == "code_postal":     data[field] = f.postcode()
        elif field == "departement":     data[field] = f.department_name()
        elif field == "region":          data[field] = f.region()
        elif field == "pays":            data[field] = "France"
        elif field == "nom_entreprise":  data[field] = f.company()
        elif field == "siret_fake":      data[field] = _make_siret()
        elif field == "siren_fake":      data[field] = " ".join([str(f.random_digit()) for _ in range(9)][:3])
        elif field == "email_pro":       data[field] = f.company_email()
        elif field == "secteur":         data[field] = f.job()
        elif field == "site_web":        data[field] = f.url()
        elif field == "iban_fake":       data[field] = _make_iban()
        elif field == "bic_fake":        data[field] = f.swift8()
        elif field == "numero_carte":    data[field] = f.credit_card_number(card_type="visa")
        elif field == "date_expiration_carte": data[field] = f.credit_card_expire()
        elif field == "username":        data[field] = f.user_name()
        elif field == "password_fake":   data[field] = f.password(length=16, special_chars=True)
        elif field == "user_agent":      data[field] = f.user_agent()
        elif field == "ipv4":            data[field] = f.ipv4_public()
        elif field == "ipv6":            data[field] = f.ipv6()
        elif field == "url":             data[field] = f.url()
        elif field == "domaine":         data[field] = f.domain_name()
        elif field == "titre":           data[field] = f.catch_phrase()
        elif field == "paragraphe":      data[field] = f.paragraph(nb_sentences=4)
        elif field == "phrase":          data[field] = f.sentence()
        elif field == "mots":            data[field] = f.words(nb=5)

    return data


@app.get("/")
def root():
    return {
        "service": "x402 Fake Data FR",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.001 USDC/appel",
        "endpoint": "POST /generate",
        "profils": list(PROFILES.keys()),
        "max_count": 20,
        "docs": "/docs",
        "tagline": "Generate realistic French fake data — names, addresses, SIRET, IBAN...",
        "curl_example": "curl https://x402-fakedata-fr.suretat.com/generate -H 'Content-Type: application/json' -d '{\"types\": [\"person\", \"address\", \"company\"], \"count\": 3}'",
        "try_it": "https://x402-fakedata-fr.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/generate" and request.method == "POST":
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
                        "description": "Fake Data FR — 0.001 USDC",
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
def generate(req: FakeDataRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if req.seed is not None:
        Faker.seed(req.seed)

    profil = req.profil if req.profil in PROFILES else "personne"
    records = [generate_record(profil) for _ in range(req.count)]

    return {
        "profil": profil,
        "count": len(records),
        "data": records[0] if req.count == 1 else records,
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
            "resource": f"https://{host}/generate",
            "description": "x402 Fake Data FR",
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
    uvicorn.run(app, host="0.0.0.0", port=3045)
