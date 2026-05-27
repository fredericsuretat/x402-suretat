from __future__ import annotations
import logging
import math
import os
import re
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-textstats")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Text Statistics", version="1.0.0")

# French syllable counting heuristic
def count_syllables_fr(word: str) -> int:
    word = word.lower()
    word = re.sub(r'[^a-zàâçéèêëîïôùûüæœ]', '', word)
    if not word:
        return 0
    # Count vowel groups
    vowels = "aeiouyàâéèêëîïôùûüæœ"
    count = len(re.findall(f'[{vowels}]+', word))
    # Silent e at end
    if word.endswith('e') and count > 1:
        count -= 1
    return max(1, count)


def flesch_kincaid_fr(words: list[str], sentences: int) -> float:
    """Approximation du score Flesch-Kincaid adapté au français."""
    if not words or sentences == 0:
        return 0.0
    syllables = sum(count_syllables_fr(w) for w in words)
    asl = len(words) / sentences  # avg sentence length
    asw = syllables / len(words)  # avg syllables per word
    # Adaptation pour le français (coefficients Kandel & Moles)
    score = 207 - (1.015 * asl) - (73.6 * asw)
    return round(max(0.0, min(100.0, score)), 1)


FLESCH_LEVELS = [
    (90, "Très facile (enfants)"),
    (80, "Facile (ados)"),
    (70, "Assez facile"),
    (60, "Standard"),
    (50, "Assez difficile"),
    (30, "Difficile (universitaire)"),
    (0, "Très difficile (expert)"),
]


class TextRequest(BaseModel):
    text: str = Field(..., description="Texte à analyser", max_length=500_000)
    lang: str = Field(default="fr", description="Langue du texte (fr, en)")


@app.get("/")
def root():
    return {
        "service": "x402 Text Statistics",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/analyse",
        "endpoint": "POST /analyze",
        "metriques": ["mots", "phrases", "paragraphes", "caractères", "temps de lecture", "score Flesch", "mots fréquents"],
        "docs": "/docs",
        "tagline": "Analyze text — word count, readability, frequency, language detection",
        "curl_example": "curl https://x402-textstats.suretat.com/analyze -H 'Content-Type: application/json' -d '{\"text\": \"The quick brown fox jumps over the lazy dog.\"}'",
        "try_it": "https://x402-textstats.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/analyze" and request.method == "POST":
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
                        "description": "Text statistics — 0.0005 USDC",
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


@app.post("/analyze")
def analyze_text(req: TextRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    text = req.text

    # Basic counts
    chars = len(text)
    chars_no_spaces = len(text.replace(" ", ""))
    words = re.findall(r'\b\w+\b', text)
    word_count = len(words)
    unique_words = len(set(w.lower() for w in words))

    # Sentences (rough approximation)
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    sentence_count = max(1, len(sentences))

    # Paragraphs
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    paragraph_count = max(1, len(paragraphs))

    # Reading time (avg 200-250 wpm for FR)
    reading_speed_wpm = 230
    reading_seconds = int(word_count / reading_speed_wpm * 60)
    if reading_seconds < 60:
        reading_time = f"{reading_seconds} sec"
    else:
        reading_time = f"{reading_seconds // 60} min {reading_seconds % 60} sec"

    # Avg sentence & word length
    avg_sentence_length = round(word_count / sentence_count, 1)
    avg_word_length = round(chars_no_spaces / max(1, word_count), 1)

    # Flesch score
    flesch = flesch_kincaid_fr(words, sentence_count)
    flesch_label = next((label for threshold, label in FLESCH_LEVELS if flesch >= threshold), "Très difficile (expert)")

    # Top 10 most frequent words (excluding short stop words)
    stop_words = {"le","la","les","de","du","des","en","et","à","un","une","que","qui","par","pour","est","son","sa","ses","il","elle","ils","elles","ce","cet","cette","ces","je","tu","nous","vous","on","avec","dans","sur","au","aux","ou","mais","si","car","donc","or","ni","ne","se","lui","leur","leurs","mes","tes","mon","ton","ma","ta","plus","comme","bien","tout","cette","peut","pas","y","avoir","être","fait","faire","dit","très","après","avant","aussi","même","où","quand","dont","which","the","a","an","in","is","of","to","and","or","for","on","at","by","from","that","this","with","as","be","was","are","were","been","have","has","had","do","did","will","would","can","could","should","may","might","shall"}
    word_freq: dict[str, int] = {}
    for w in words:
        wl = w.lower()
        if len(wl) > 3 and wl not in stop_words:
            word_freq[wl] = word_freq.get(wl, 0) + 1
    top_words = sorted(word_freq.items(), key=lambda x: -x[1])[:10]

    # Lexical diversity (TTR)
    ttr = round(unique_words / max(1, word_count), 3)

    return {
        "caracteres": chars,
        "caracteres_sans_espaces": chars_no_spaces,
        "mots": word_count,
        "mots_uniques": unique_words,
        "diversite_lexicale": ttr,
        "phrases": sentence_count,
        "paragraphes": paragraph_count,
        "longueur_moy_phrase": avg_sentence_length,
        "longueur_moy_mot": avg_word_length,
        "temps_lecture": reading_time,
        "temps_lecture_secondes": reading_seconds,
        "score_flesch": flesch,
        "niveau_lecture": flesch_label,
        "mots_frequents": [{"mot": w, "occurrences": c} for w, c in top_words],
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
            "resource": f"https://{host}/analyze",
            "description": "x402 Text Statistics",
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
    uvicorn.run(app, host="0.0.0.0", port=3055)
