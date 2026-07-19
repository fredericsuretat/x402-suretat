from __future__ import annotations
import os, re, time, unicodedata
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List

PORT = int(os.getenv("PORT", "3116"))
PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
HOST_DOMAIN = os.getenv("HOST_DOMAIN", "x402-french-nlp.suretat.com")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 French NLP", version="1.0.0")

STOPWORDS_FR = frozenset([
    "le","la","les","de","du","des","un","une","et","est","en","au","aux","pour","par",
    "sur","dans","avec","que","qui","ce","se","sa","son","ses","ou","à","il","elle",
    "nous","vous","ils","elles","on","y","je","tu","me","te","lui","leur","leurs",
    "mon","ma","mes","ton","ta","tes","notre","votre","vos","même","plus","bien",
    "très","aussi","car","si","mais","donc","or","ni","ne","pas","plus","rien",
    "tout","toute","tous","toutes","autre","autres","cette","ces","cet","dont",
    "quoi","quel","quelle","quels","quelles","que","quand","comment","pourquoi",
    "combien","où","après","avant","pendant","depuis","jusqu","entre","parmi",
    "selon","chez","vers","sous","hors","lors","dès","via","être","avoir","faire",
    "pouvoir","vouloir","devoir","aller","venir","voir","savoir","falloir",
    "y","en","qu","s","c","j","m","t","l","d","n",
])

# Simple French lemmatization rules
LEMMA_SUFFIXES = [
    (r"ations$", "ation"), (r"ements$", "ement"), (r"iques$", "ique"),
    (r"eurs$", "eur"), (r"euses$", "euse"), (r"ables$", "able"),
    (r"ibles$", "ible"), (r"ités$", "ité"), (r"ages$", "age"),
    (r"istes$", "iste"), (r"ismes$", "isme"), (r"aires$", "aire"),
    (r"oires$", "oire"), (r"aux$", "al"), (r"eaux$", "eau"),
    (r"iers$", "ier"), (r"ières$", "ière"), (r"ants$", "ant"),
    (r"antes$", "ante"), (r"ants$", "ant"), (r"ées$", "ée"),
    (r"és$", "é"), (r"ées$", "ée"),
    (r"s$", ""),
]

# Named entity patterns for French
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4})\b",
    re.I
)
MONEY_RE = re.compile(r"\b\d+(?:[.,]\d+)*\s*(?:€|EUR|USD|\$|£)\b|\b(?:€|EUR|USD|\$|£)\s*\d+(?:[.,]\d+)*\b", re.I)
PERCENT_RE = re.compile(r"\b\d+(?:[.,]\d+)?%\b")
PHONE_RE = re.compile(r"(?:\+33|0)[1-9](?:[\s.\-]?\d{2}){4}")
EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
URL_RE = re.compile(r"https?://[^\s]+")
CAPITALIZED_RE = re.compile(r"\b[A-ZÀÂÄÉÈÊËÏÎÔÙÛÜ][a-zàâäéèêëïîôùûü]+(?:\s+[A-ZÀÂÄÉÈÊËÏÎÔÙÛÜ][a-zàâäéèêëïîôùûü]+)+\b")

# French POS indicators (simplified)
VERB_ENDINGS = re.compile(r"(?:er|ir|re|ais|ait|ons|ez|ont|ant|é|ée|és|ées|era|erait|aient)$")
ADJ_ENDINGS = re.compile(r"(?:eux|euse|al|ale|if|ive|ble|ique|aire|oire|ant|ante|ent|ente)$")
NOUN_ENDINGS = re.compile(r"(?:tion|sion|ment|age|eur|euse|iste|isme|ité|té|esse|ance|ence|oire|ure)$")


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def tokenize(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())


def lemmatize(word: str) -> str:
    if len(word) <= 4:
        return word
    for pattern, replacement in LEMMA_SUFFIXES:
        result = re.sub(pattern, replacement, word)
        if result != word and len(result) >= 3:
            return result
    return word


def remove_stopwords(tokens: List[str]) -> List[str]:
    return [t for t in tokens if t not in STOPWORDS_FR and len(t) > 1]


def extract_entities(text: str) -> dict:
    return {
        "dates": DATE_RE.findall(text),
        "money": MONEY_RE.findall(text),
        "percentages": PERCENT_RE.findall(text),
        "phones": PHONE_RE.findall(text),
        "emails": EMAIL_RE.findall(text),
        "urls": URL_RE.findall(text),
        "proper_nouns": list(set(CAPITALIZED_RE.findall(text)))[:20],
    }


def compute_frequencies(tokens: List[str]) -> List[dict]:
    freq: dict = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    return sorted([{"word": w, "count": c} for w, c in freq.items()], key=lambda x: -x["count"])[:20]


def guess_pos(word: str) -> str:
    if VERB_ENDINGS.search(word):
        return "V"
    if ADJ_ENDINGS.search(word):
        return "ADJ"
    if NOUN_ENDINGS.search(word):
        return "N"
    if word[0].isupper():
        return "NPR"
    return "?"


def _make_402(host: str, endpoint: str = "/analyze") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "French NLP: tokenize, lemmatize, stopwords, NER, POS, frequency",
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
            return _make_402(request.headers.get("host", HOST_DOMAIN))
    return await call_next(request)


class NLPRequest(BaseModel):
    text: str
    operations: Optional[List[str]] = None  # tokenize, lemmatize, stopwords, ner, pos, frequency


@app.get("/")
def root():
    return {
        "service": "x402 French NLP",
        "description": "French NLP pipeline: tokenization, lemmatization, stopword removal, NER, POS tagging, word frequency.",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/call",
        "operations": ["tokenize", "lemmatize", "stopwords", "ner", "pos", "frequency"],
        "endpoint": "POST /analyze",
        "docs": "/docs",
    }


@app.post("/analyze")
def analyze(req: NLPRequest):
    if not req.text or len(req.text.strip()) < 3:
        return JSONResponse(status_code=400, content={"error": "text too short"})

    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    text = normalize(req.text[:5000])
    ops = set(req.operations or ["tokenize", "lemmatize", "stopwords", "ner", "frequency"])
    result: dict = {"word_count": len(text.split()), "char_count": len(text)}

    raw_tokens = tokenize(text)
    if "tokenize" in ops:
        result["tokens"] = raw_tokens[:200]

    filtered = remove_stopwords(raw_tokens)
    if "stopwords" in ops:
        result["tokens_no_stopwords"] = filtered[:200]
        result["stopwords_removed"] = len(raw_tokens) - len(filtered)

    if "lemmatize" in ops:
        lemmas = [lemmatize(t) for t in filtered]
        result["lemmas"] = lemmas[:200]

    if "pos" in ops:
        result["pos_tags"] = [{"word": t, "pos": guess_pos(t)} for t in filtered[:50]]

    if "ner" in ops:
        result["entities"] = extract_entities(text)

    if "frequency" in ops:
        result["top_words"] = compute_frequencies(filtered)

    return result


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", HOST_DOMAIN)
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/analyze",
        "description": "French NLP: tokenize, lemmatize, stopwords, NER, POS, frequency",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")
