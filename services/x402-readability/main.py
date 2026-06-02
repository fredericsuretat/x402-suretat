from __future__ import annotations
import logging
import os
import re
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-readability")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Readability Scorer", version="1.0.0")


def syllable_count(word: str) -> int:
    word = word.lower().strip(".,!?;:")
    word = re.sub(r"[^a-z]", "", word)
    if not word:
        return 0
    if len(word) <= 3:
        return 1
    word = re.sub(r"e$", "", word)
    count = len(re.findall(r"[aeiou]+", word))
    return max(1, count)


def analyze(text: str) -> dict:
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    words = re.findall(r"\b[a-zA-Z]+\b", text)

    if not words:
        return {"error": "No words found in text"}
    if not sentences:
        sentences = [text]

    n_sentences = len(sentences)
    n_words = len(words)
    n_syllables = sum(syllable_count(w) for w in words)
    n_chars = sum(len(w) for w in words)
    n_complex = sum(1 for w in words if syllable_count(w) >= 3)

    avg_sentence_len = n_words / n_sentences
    avg_syllables = n_syllables / n_words
    avg_word_len = n_chars / n_words

    # Flesch Reading Ease (206.835 - 1.015*(words/sentences) - 84.6*(syllables/words))
    flesch = 206.835 - (1.015 * avg_sentence_len) - (84.6 * avg_syllables)
    flesch = max(0.0, min(100.0, flesch))

    # Flesch-Kincaid Grade Level
    fk_grade = (0.39 * avg_sentence_len) + (11.8 * avg_syllables) - 15.59

    # Gunning Fog Index
    fog = 0.4 * (avg_sentence_len + 100 * n_complex / n_words)

    # SMOG Grade (simplified, needs ≥30 sentences for accuracy)
    smog = 3.1291 + 1.043 * (n_complex ** 0.5 * (30 / n_sentences) ** 0.5) if n_sentences >= 3 else None

    # Coleman-Liau Index
    cli_l = (n_chars / n_words) * 100
    cli_s = (n_sentences / n_words) * 100
    coleman_liau = (0.0588 * cli_l) - (0.296 * cli_s) - 15.8

    # Automated Readability Index
    ari = (4.71 * avg_word_len) + (0.5 * avg_sentence_len) - 21.43

    def reading_ease_label(score: float) -> str:
        if score >= 90: return "Very Easy (5th grade)"
        if score >= 80: return "Easy (6th grade)"
        if score >= 70: return "Fairly Easy (7th grade)"
        if score >= 60: return "Standard (8th-9th grade)"
        if score >= 50: return "Fairly Difficult (10th-12th grade)"
        if score >= 30: return "Difficult (college)"
        return "Very Difficult (college graduate)"

    return {
        "counts": {
            "words": n_words,
            "sentences": n_sentences,
            "syllables": n_syllables,
            "characters": n_chars,
            "complex_words": n_complex,
        },
        "averages": {
            "words_per_sentence": round(avg_sentence_len, 2),
            "syllables_per_word": round(avg_syllables, 2),
            "chars_per_word": round(avg_word_len, 2),
        },
        "scores": {
            "flesch_reading_ease": round(flesch, 2),
            "flesch_kincaid_grade": round(fk_grade, 2),
            "gunning_fog": round(fog, 2),
            "smog_grade": round(smog, 2) if smog else None,
            "coleman_liau": round(coleman_liau, 2),
            "automated_readability_index": round(ari, 2),
        },
        "interpretation": {
            "reading_ease": reading_ease_label(flesch),
            "grade_level": f"~grade {max(1, round(fk_grade))}",
            "note": "SMOG requires ≥30 sentences for accuracy" if n_sentences < 30 else None,
        },
    }


class ReadabilityRequest(BaseModel):
    text: str = Field(..., description="Text to analyze", max_length=200_000)


@app.get("/")
def root():
    return {
        "service": "x402 Readability Scorer",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/call",
        "endpoint": "POST /score",
        "scores": ["flesch_reading_ease", "flesch_kincaid_grade", "gunning_fog", "smog_grade", "coleman_liau", "ari"],
        "tagline": "Readability scores — Flesch, Kincaid, Gunning Fog, SMOG, Coleman-Liau, ARI",
        "curl_example": "curl https://x402-readability.suretat.com/score -H 'Content-Type: application/json' -d '{\"text\": \"The cat sat on the mat.\"}'",
        "try_it": "https://x402-readability.suretat.com/docs",
        "docs": "/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.get("/health")
async def health():
    return {"ok": True}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/score" and request.method == "POST":
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
                        "resource": "https://" + request.headers.get("host", "") + "/score",
                        "description": "Text readability scores — Flesch, Kincaid, Fog, SMOG, ARI",
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


@app.post("/score")
def score(req: ReadabilityRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    return analyze(req.text)


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-readability.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/score",
            "description": "Text readability scores — Flesch, Kincaid, Fog, SMOG, ARI",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3081, proxy_headers=True, forwarded_allow_ips="*")
