from __future__ import annotations
import os, time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from langdetect import detect, detect_langs, LangDetectException

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Lang Detect", version="1.0.0")

LANGUAGE_NAMES = {
    "af": "Afrikaans", "ar": "Arabic", "bg": "Bulgarian", "bn": "Bengali",
    "ca": "Catalan", "cs": "Czech", "cy": "Welsh", "da": "Danish",
    "de": "German", "el": "Greek", "en": "English", "es": "Spanish",
    "et": "Estonian", "fa": "Persian", "fi": "Finnish", "fr": "French",
    "gu": "Gujarati", "he": "Hebrew", "hi": "Hindi", "hr": "Croatian",
    "hu": "Hungarian", "id": "Indonesian", "it": "Italian", "ja": "Japanese",
    "kn": "Kannada", "ko": "Korean", "lt": "Lithuanian", "lv": "Latvian",
    "mk": "Macedonian", "ml": "Malayalam", "mr": "Marathi", "ne": "Nepali",
    "nl": "Dutch", "no": "Norwegian", "pa": "Punjabi", "pl": "Polish",
    "pt": "Portuguese", "ro": "Romanian", "ru": "Russian", "sk": "Slovak",
    "sl": "Slovenian", "so": "Somali", "sq": "Albanian", "sv": "Swedish",
    "sw": "Swahili", "ta": "Tamil", "te": "Telugu", "th": "Thai",
    "tl": "Filipino", "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu",
    "vi": "Vietnamese", "zh-cn": "Chinese (Simplified)", "zh-tw": "Chinese (Traditional)",
}


def _make_402(host: str, endpoint: str = "/detect") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "Language detection from text",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/detect" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-lang-detect.suretat.com"))
    return await call_next(request)


class DetectRequest(BaseModel):
    text: str
    top_n: Optional[int] = 3


@app.get("/")
def root():
    return {"service": "x402 Lang Detect", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/detect")
def detect_language(req: DetectRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if not req.text or not req.text.strip():
        return JSONResponse(status_code=400, content={"error": "text cannot be empty"})

    if len(req.text.strip()) < 3:
        return JSONResponse(status_code=400, content={"error": "text too short for reliable detection"})

    try:
        langs = detect_langs(req.text)
    except LangDetectException as e:
        return JSONResponse(status_code=422, content={"error": f"Detection failed: {str(e)}"})

    top_n = min(req.top_n or 3, len(langs))
    top = langs[:top_n]

    main_lang = top[0]
    alternatives = []
    for lang_prob in top[1:]:
        alternatives.append({
            "language": lang_prob.lang,
            "language_name": LANGUAGE_NAMES.get(lang_prob.lang, lang_prob.lang),
            "confidence": round(lang_prob.prob, 4),
        })

    return {
        "language": main_lang.lang,
        "language_name": LANGUAGE_NAMES.get(main_lang.lang, main_lang.lang),
        "confidence": round(main_lang.prob, 4),
        "alternatives": alternatives,
        "text_length": len(req.text),
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-lang-detect.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/detect",
        "description": "Language detection from text",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3105, proxy_headers=True, forwarded_allow_ips="*")
