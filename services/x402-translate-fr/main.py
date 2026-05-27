"""
x402 Translate FR — Traduction via DeepL API
Langues supportées: 30 langues, qualité professionnelle
Prix: 0.001 USDC / appel (jusqu'à 5000 caractères)
"""
from __future__ import annotations
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

WALLET       = os.getenv("WALLET_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
FACILITATOR  = os.getenv("FACILITATOR_URL", "https://api.cdp.coinbase.com/platform/v2/x402")
USDC_BASE    = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "")
DEEPL_URL    = "https://api-free.deepl.com/v2/translate"
MAX_CHARS    = 5000

payments_total = 0
payments_log: list = []

# DeepL supported languages (lowercase input → uppercase DeepL code)
SUPPORTED_LANGS = {
    "ar": "AR",  "bg": "BG",  "cs": "CS",  "da": "DA",
    "de": "DE",  "el": "EL",  "en": "EN",  "es": "ES",
    "et": "ET",  "fi": "FI",  "fr": "FR",  "hu": "HU",
    "id": "ID",  "it": "IT",  "ja": "JA",  "ko": "KO",
    "lt": "LT",  "lv": "LV",  "nb": "NB",  "nl": "NL",
    "pl": "PL",  "pt": "PT",  "ro": "RO",  "ru": "RU",
    "sk": "SK",  "sl": "SL",  "sv": "SV",  "tr": "TR",
    "uk": "UK",  "zh": "ZH",
}

LANG_NAMES = {
    "ar": "Arabic", "bg": "Bulgarian", "cs": "Czech", "da": "Danish",
    "de": "German", "el": "Greek", "en": "English", "es": "Spanish",
    "et": "Estonian", "fi": "Finnish", "fr": "French", "hu": "Hungarian",
    "id": "Indonesian", "it": "Italian", "ja": "Japanese", "ko": "Korean",
    "lt": "Lithuanian", "lv": "Latvian", "nb": "Norwegian", "nl": "Dutch",
    "pl": "Polish", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian",
    "sk": "Slovak", "sl": "Slovenian", "sv": "Swedish", "tr": "Turkish",
    "uk": "Ukrainian", "zh": "Chinese (Simplified)",
}

PAYMENT_REQUIREMENTS = {
    "scheme": "exact",
    "network": "base",
    "maxAmountRequired": PRICE_ATOMIC,
    "resource": "https://x402-translate-fr.suretat.com/translate",
    "description": "Traduction de texte — 30 langues via DeepL",
    "mimeType": "application/json",
    "payTo": WALLET,
    "maxTimeoutSeconds": 300,
    "asset": USDC_BASE,
    "extra": {
        "name": "USD Coin",
        "version": "2",
        "bazaar": {
            "bodyType": "json",
            "input": {"text": "Bonjour le monde", "source": "fr", "target": "en"},
            "inputSchema": {
                "properties": {
                    "text":   {"type": "string", "description": "Texte à traduire (max 5000 caractères)"},
                    "source": {"type": "string", "description": "Code langue source (fr, en, es...) ou 'auto'"},
                    "target": {"type": "string", "description": "Code langue cible (en, es, de...)"},
                },
                "required": ["text", "target"],
            },
            "output": {
                "example": {
                    "translated_text": "Hello World",
                    "source_detected": "FR",
                    "target": "en",
                    "chars": 16,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    key_status = "OK" if DEEPL_API_KEY else "MANQUANTE"
    print(f"[x402-translate] Wallet: {WALLET} | DeepL API key: {key_status}")
    yield


app = FastAPI(title="x402 Translate FR", version="2.0.0", lifespan=lifespan)


class TranslateRequest(BaseModel):
    text: str
    source: str = "auto"
    target: str


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if not request.url.path.startswith("/translate"):
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
    print(f"[x402-translate] PAIEMENT #{payments_total}")
    return response


@app.get("/")
async def root():
    return {
        "service": "x402 Translate FR",
        "protocol": "x402 (Base/USDC)",
        "version": "2.0.0",
        "engine": "DeepL API",
        "price": "0.001 USDC / appel (jusqu'à 5000 caractères)",
        "endpoint": "POST /translate",
        "body": {"text": "string", "source": "fr (ou 'auto')", "target": "en"},
        "languages": len(SUPPORTED_LANGS),
        "docs": "/docs",
        "tagline": "Translate text to/from French using DeepL — 30+ languages supported",
        "curl_example": "curl https://x402-translate-fr.suretat.com/translate -H 'Content-Type: application/json' -d '{\"text\": \"Hello, how are you?\", \"target_lang\": \"FR\"}'",
        "try_it": "https://x402-translate-fr.suretat.com/docs",
    }


@app.post("/translate")
async def translate(payload: TranslateRequest):
    if not DEEPL_API_KEY:
        return JSONResponse(status_code=503, content={"error": "Clé DeepL non configurée"})

    text = payload.text.strip()
    if not text:
        return JSONResponse(status_code=400, content={"error": "Champ 'text' requis"})
    if len(text) > MAX_CHARS:
        return JSONResponse(
            status_code=400,
            content={"error": f"Texte trop long: {len(text)} car. (max {MAX_CHARS})"},
        )

    target = payload.target.strip().lower()
    if target not in SUPPORTED_LANGS:
        return JSONResponse(
            status_code=400,
            content={"error": f"Langue cible non supportée: '{target}'", "supported": list(SUPPORTED_LANGS.keys())},
        )

    source = payload.source.strip().lower() if payload.source else "auto"
    if source != "auto" and source not in SUPPORTED_LANGS:
        return JSONResponse(
            status_code=400,
            content={"error": f"Langue source non supportée: '{source}'", "supported": list(SUPPORTED_LANGS.keys()) + ["auto"]},
        )

    params: dict = {
        "text": text,
        "target_lang": SUPPORTED_LANGS[target],
    }
    if source != "auto":
        params["source_lang"] = SUPPORTED_LANGS[source]

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                DEEPL_URL,
                headers={"Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"},
                data=params,
            )
            if resp.status_code == 403:
                return JSONResponse(status_code=502, content={"error": "Clé DeepL invalide"})
            if resp.status_code == 456:
                return JSONResponse(status_code=502, content={"error": "Quota DeepL dépassé (500k car./mois)"})
            if resp.status_code != 200:
                return JSONResponse(
                    status_code=502,
                    content={"error": "Erreur DeepL", "detail": resp.text[:200]},
                )
            data = resp.json()
            translation = data["translations"][0]
            return {
                "translated_text": translation["text"],
                "source_detected": translation.get("detected_source_language", source.upper()),
                "target": target,
                "target_lang": LANG_NAMES.get(target, target),
                "chars": len(text),
            }
        except httpx.TimeoutException:
            return JSONResponse(status_code=504, content={"error": "Timeout DeepL"})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": f"Erreur: {str(e)[:100]}"})


@app.get("/languages")
async def languages():
    return {"languages": [{"code": k, "name": LANG_NAMES[k]} for k in SUPPORTED_LANGS]}


@app.get("/stats")
async def stats():
    return {"service": "x402-translate-fr", "engine": "DeepL", "payments_total": payments_total, "last_payments": payments_log[-10:]}

@app.get("/.well-known/x402.json")
async def x402_well_known():
    return {"x402Version": 1, "accepts": [PAYMENT_REQUIREMENTS]}

@app.get("/.well-known/x402")
async def x402_well_known_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/.well-known/x402.json")

