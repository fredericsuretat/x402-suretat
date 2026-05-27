from __future__ import annotations
import logging
import os
import re
import time
import unicodedata
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-phonetic")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Phonetic Encoder", version="1.0.0")


# ── Soundex ───────────────────────────────────────────────────────────────────
SOUNDEX_TABLE = str.maketrans("BFPVCGJKQSXZDTLMNR", "111122222222334556")

def soundex(word: str) -> str:
    word = unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode()
    word = re.sub(r"[^A-Za-z]", "", word).upper()
    if not word:
        return ""
    first = word[0]
    coded = word.translate(SOUNDEX_TABLE)
    # Remove duplicate adjacent digits and zeros
    result = first
    prev = coded[0]
    for ch in coded[1:]:
        if ch != "0" and ch != prev:
            result += ch
        prev = ch
    return (result + "000")[:4]


# ── Metaphone (simplified) ────────────────────────────────────────────────────
def metaphone(word: str) -> str:
    word = unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode()
    word = re.sub(r"[^A-Za-z]", "", word).upper()
    if not word:
        return ""
    # Drop trailing S, ES, ED
    word = re.sub(r"(S|ES|ED)$", "", word)
    # Initial special cases
    word = re.sub(r"^(AE|GN|KN|PN|WR)", lambda m: m.group()[1:], word)
    # Convert
    result = []
    i = 0
    while i < len(word):
        c = word[i]
        nxt = word[i+1] if i+1 < len(word) else ""
        if c in "AEIOU":
            if i == 0: result.append(c)
        elif c == "B":
            if not (i > 0 and word[i-1] == "M"): result.append("B")
        elif c == "C":
            if nxt in "EIY": result.append("S")
            else: result.append("K")
        elif c == "D":
            if nxt == "G" and i+2 < len(word) and word[i+2] in "EIY":
                result.append("J"); i += 1
            else: result.append("T")
        elif c == "G":
            if nxt in "EIY": result.append("J")
            elif nxt != "H": result.append("K")
        elif c == "H":
            if nxt not in "AEIOU" and (i == 0 or word[i-1] not in "AEIOU"): pass
            else: result.append("H")
        elif c == "K":
            if i == 0 or word[i-1] != "C": result.append("K")
        elif c == "P":
            if nxt == "H": result.append("F"); i += 1
            else: result.append("P")
        elif c == "Q": result.append("K")
        elif c == "S":
            if nxt in ("IO", "IA"): result.append("X")
            else: result.append("S")
        elif c == "T":
            if nxt in ("IO", "IA"): result.append("X")
            elif nxt == "H": result.append("0"); i += 1
            elif not (nxt == "C" and i+2 < len(word) and word[i+2] == "H"): result.append("T")
        elif c == "V": result.append("F")
        elif c == "W":
            if nxt in "AEIOU": result.append("W")
        elif c == "X": result.extend(["K", "S"])
        elif c == "Y":
            if nxt in "AEIOU": result.append("Y")
        elif c == "Z": result.append("S")
        elif c in "FLJMNR": result.append(c)
        i += 1
    return "".join(result)


# ── Double Metaphone (simplified) ─────────────────────────────────────────────
def double_metaphone(word: str) -> tuple[str, str]:
    primary = metaphone(word)
    # For simplicity, secondary is Soundex result (a rough approximation)
    return primary, soundex(word)


# ── NYSIIS ────────────────────────────────────────────────────────────────────
def nysiis(word: str) -> str:
    word = unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode()
    word = re.sub(r"[^A-Za-z]", "", word).upper()
    if not word:
        return ""
    # Translate first characters
    word = re.sub(r"^MAC", "MCC", word)
    word = re.sub(r"^KN", "N", word)
    word = re.sub(r"^K", "C", word)
    word = re.sub(r"(PH|PF)$", "FF", word)
    word = re.sub(r"(IE)$", "Y", word)
    word = re.sub(r"(EE|IE)$", "Y", word)
    word = re.sub(r"(DT|RT|RD|NT|ND)$", "D", word)
    first = word[0]
    # Process remaining
    word = word[1:]
    word = word.replace("EV", "AF").replace("KN", "N").replace("SCH", "S")
    word = re.sub(r"[EI]([^AEIOU])", r"A\1", word)
    word = word.replace("Q", "G").replace("Z", "S").replace("M", "N")
    word = word.replace("KN", "N").replace("K", "C")
    word = word.replace("SCH", "S").replace("PH", "F")
    # Remove trailing S, AY
    word = re.sub(r"S$", "", word)
    word = re.sub(r"AY$", "Y", word)
    word = re.sub(r"A$", "", word)
    result = first + word
    # Collapse duplicates
    collapsed = result[0]
    for ch in result[1:]:
        if ch != collapsed[-1]:
            collapsed += ch
    # Remove vowels except first
    final = collapsed[0]
    for ch in collapsed[1:]:
        if ch not in "AEIOU":
            final += ch
    return final[:6]


class PhoneticRequest(BaseModel):
    text: str = Field(..., description="Word or phrase to encode", max_length=500)
    algorithms: list[Literal["soundex", "metaphone", "double_metaphone", "nysiis"]] = Field(
        default=["soundex", "metaphone"], description="Algorithms to apply"
    )


@app.get("/")
def root():
    return {
        "service": "x402 Phonetic Encoder",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/call",
        "endpoint": "POST /encode",
        "algorithms": ["soundex", "metaphone", "double_metaphone", "nysiis"],
        "tagline": "Phonetic encoding — Soundex, Metaphone, Double Metaphone, NYSIIS for fuzzy name matching",
        "curl_example": "curl https://x402-phonetic.suretat.com/encode -H 'Content-Type: application/json' -d '{\"text\": \"Smith\", \"algorithms\": [\"soundex\", \"metaphone\"]}'",
        "try_it": "https://x402-phonetic.suretat.com/docs",
        "docs": "/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/encode" and request.method == "POST":
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
                        "resource": "https://" + request.headers.get("host", "") + "/encode",
                        "description": "Phonetic encoding — Soundex, Metaphone, NYSIIS",
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


@app.post("/encode")
def encode(req: PhoneticRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    words = req.text.strip().split()
    result: dict = {"input": req.text, "words": []}

    for word in words:
        entry: dict = {"word": word}
        if "soundex" in req.algorithms:
            entry["soundex"] = soundex(word)
        if "metaphone" in req.algorithms:
            entry["metaphone"] = metaphone(word)
        if "double_metaphone" in req.algorithms:
            p, s = double_metaphone(word)
            entry["double_metaphone"] = {"primary": p, "secondary": s}
        if "nysiis" in req.algorithms:
            entry["nysiis"] = nysiis(word)
        result["words"].append(entry)

    # For multi-word input, also provide phrase-level codes
    if len(words) > 1:
        result["phrase"] = {
            algo: " ".join(
                soundex(w) if algo == "soundex"
                else metaphone(w) if algo == "metaphone"
                else nysiis(w) if algo == "nysiis"
                else double_metaphone(w)[0]
                for w in words
            )
            for algo in req.algorithms
        }

    return result


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-phonetic.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/encode",
            "description": "Phonetic encoding — Soundex, Metaphone, NYSIIS",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3080, proxy_headers=True, forwarded_allow_ips="*")
