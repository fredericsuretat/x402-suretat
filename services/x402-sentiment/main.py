from __future__ import annotations
import os, time, re
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Sentiment", version="1.0.0")

# Embedded lexicon — VADER-like, EN + FR
POSITIVE_EN = {
    "good": 1.9, "great": 2.5, "excellent": 3.0, "amazing": 3.2, "wonderful": 3.0,
    "fantastic": 3.0, "love": 2.5, "like": 1.5, "best": 2.8, "happy": 2.2,
    "perfect": 2.9, "awesome": 3.1, "brilliant": 2.8, "superb": 2.8, "outstanding": 2.9,
    "beautiful": 2.5, "nice": 1.8, "pleasant": 1.9, "enjoy": 2.0, "fun": 1.9,
    "delightful": 2.7, "satisfied": 2.0, "positive": 1.9, "success": 2.1, "win": 2.0,
    "joy": 2.6, "excited": 2.3, "glad": 2.0, "pleased": 1.9, "thankful": 2.2,
    "grateful": 2.4, "impressive": 2.3, "recommend": 2.0, "helpful": 1.8, "clear": 1.2,
    "fast": 1.3, "easy": 1.5, "safe": 1.4, "reliable": 1.7, "innovative": 1.8,
}
NEGATIVE_EN = {
    "bad": -1.9, "terrible": -3.0, "awful": -2.9, "horrible": -3.1, "hate": -2.8,
    "worst": -3.0, "poor": -1.9, "disappointing": -2.3, "disgusting": -2.8, "wrong": -1.6,
    "fail": -2.0, "failure": -2.2, "ugly": -2.1, "sad": -2.0, "angry": -2.3,
    "boring": -1.8, "broken": -2.1, "useless": -2.4, "slow": -1.5, "difficult": -1.3,
    "confusing": -1.6, "frustrating": -2.3, "annoying": -2.0, "waste": -2.2, "stupid": -2.5,
    "dumb": -2.3, "problematic": -1.8, "unreliable": -2.0, "harmful": -2.5, "dangerous": -2.3,
    "not": -0.8, "never": -0.7, "no": -0.5, "neither": -0.5, "nobody": -0.5,
    "nothing": -0.5, "without": -0.4,
}
POSITIVE_FR = {
    "bon": 1.9, "bien": 1.7, "excellent": 3.0, "super": 2.5, "magnifique": 2.8,
    "fantastique": 3.0, "aimer": 2.5, "adorer": 2.8, "parfait": 2.9, "génial": 2.9,
    "incroyable": 2.7, "merveilleux": 2.9, "formidable": 2.7, "heureux": 2.3, "satisfait": 2.0,
    "réussi": 2.1, "bravo": 2.5, "félicitations": 2.8, "content": 2.0, "joie": 2.6,
    "agréable": 2.0, "plaisant": 1.9, "sympa": 1.9, "rapide": 1.3, "facile": 1.5,
    "utile": 1.8, "efficace": 2.0, "fiable": 1.7, "clair": 1.2, "positif": 1.9,
}
NEGATIVE_FR = {
    "mauvais": -1.9, "terrible": -3.0, "horrible": -3.1, "affreux": -2.8, "nul": -2.3,
    "détester": -2.8, "haïr": -2.9, "pire": -3.0, "raté": -2.2, "échec": -2.3,
    "décevant": -2.3, "ennuyeux": -1.8, "lent": -1.5, "difficile": -1.3, "confus": -1.6,
    "frustrant": -2.3, "inutile": -2.4, "cassé": -2.1, "faux": -1.8, "problème": -1.5,
    "triste": -2.1, "colère": -2.3, "dangereux": -2.3, "nuisible": -2.5, "bête": -2.3,
    "pas": -0.8, "jamais": -0.7, "rien": -0.5, "sans": -0.4, "non": -0.5,
}

NEGATION_WORDS_EN = {"not", "no", "never", "neither", "nor", "don't", "won't", "can't",
                      "doesn't", "didn't", "isn't", "aren't", "wasn't", "weren't", "shouldn't"}
NEGATION_WORDS_FR = {"pas", "ne", "jamais", "rien", "ni", "non", "sans"}

INTENSIFIERS_EN = {"very": 1.3, "really": 1.2, "extremely": 1.5, "quite": 1.1, "so": 1.2,
                   "absolutely": 1.4, "totally": 1.3, "utterly": 1.4, "incredibly": 1.4}
INTENSIFIERS_FR = {"très": 1.3, "vraiment": 1.2, "extrêmement": 1.5, "tellement": 1.3,
                   "absolument": 1.4, "complètement": 1.3, "incroyablement": 1.4}


def detect_lang(text: str) -> str:
    fr_markers = ["le", "la", "les", "de", "du", "des", "est", "sont", "je", "tu", "il",
                  "elle", "nous", "vous", "ils", "elles", "et", "ou", "pas", "très", "que"]
    words = text.lower().split()
    fr_count = sum(1 for w in words if w in fr_markers)
    return "fr" if fr_count >= 2 else "en"


def analyze_sentiment(text: str, lang: str) -> dict:
    if lang == "fr":
        pos_lex = POSITIVE_FR
        neg_lex = NEGATIVE_FR
        neg_words = NEGATION_WORDS_FR
        intensifiers = INTENSIFIERS_FR
    else:
        pos_lex = POSITIVE_EN
        neg_lex = NEGATIVE_EN
        neg_words = NEGATION_WORDS_EN
        intensifiers = INTENSIFIERS_EN

    # Tokenize
    tokens = re.findall(r"\b\w+\b", text.lower())

    total_score = 0.0
    word_scores = []
    n = len(tokens)

    for i, token in enumerate(tokens):
        # Check if preceded by negation (within 3 words)
        negated = any(tokens[max(0, i-j)] in neg_words for j in range(1, 4) if i-j >= 0)
        # Check if preceded by intensifier
        intensifier = 1.0
        for j in range(1, 3):
            if i-j >= 0 and tokens[i-j] in intensifiers:
                intensifier = intensifiers[tokens[i-j]]
                break

        score = 0.0
        if token in pos_lex:
            score = pos_lex[token] * intensifier
        elif token in neg_lex:
            score = neg_lex[token] * intensifier

        if negated and score != 0:
            score = -score * 0.75

        if score != 0:
            word_scores.append({"word": token, "score": round(score, 3), "negated": negated})
            total_score += score

    # Normalize to [-1, 1]
    if len(word_scores) == 0:
        polarity = 0.0
        confidence = 0.5
    else:
        alpha = 15
        polarity = total_score / (abs(total_score) + alpha)
        polarity = max(-1.0, min(1.0, polarity))
        # Confidence based on number of sentiment words and their scores
        confidence = min(0.99, 0.5 + len(word_scores) * 0.05 + abs(polarity) * 0.3)

    if polarity > 0.05:
        label = "positive"
    elif polarity < -0.05:
        label = "negative"
    else:
        label = "neutral"

    return {
        "polarity": round(polarity, 4),
        "label": label,
        "confidence": round(confidence, 4),
        "word_count": len(tokens),
        "sentiment_words": len(word_scores),
        "top_words": sorted(word_scores, key=lambda x: abs(x["score"]), reverse=True)[:5],
    }


def _make_402(host: str, endpoint: str = "/analyze") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "Sentiment analysis (EN/FR) without heavy ML models",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/analyze" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-sentiment.suretat.com"))
    return await call_next(request)


class AnalyzeRequest(BaseModel):
    text: str
    lang: Optional[str] = "auto"


@app.get("/")
def root():
    return {"service": "x402 Sentiment", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if not req.text or not req.text.strip():
        return JSONResponse(status_code=400, content={"error": "text cannot be empty"})

    lang = req.lang or "auto"
    if lang == "auto":
        lang = detect_lang(req.text)
    elif lang not in ("fr", "en"):
        lang = "en"

    result = analyze_sentiment(req.text, lang)
    return {"text": req.text[:200] + "..." if len(req.text) > 200 else req.text,
            "lang": lang, **result}


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-sentiment.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/analyze",
        "description": "Sentiment analysis (EN/FR) without heavy ML models",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3104, proxy_headers=True, forwarded_allow_ips="*")
