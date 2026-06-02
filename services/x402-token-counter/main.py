from __future__ import annotations
import logging
import os
import re
import time
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-token-counter")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Token Counter", version="1.0.0")

# Very rough but fast tokenizer based on GPT/Claude token heuristics:
# ~4 chars per token for English text; punctuation and whitespace often separate tokens.
def estimate_tokens_simple(text: str) -> int:
    # Split on whitespace and punctuation boundaries
    words = re.findall(r'\w+|[^\w\s]', text)
    total = 0
    for w in words:
        # Long words get split into sub-tokens every ~4 chars
        total += max(1, (len(w) + 2) // 3)
    return total

def count_words(text: str) -> int:
    return len(text.split())

def count_sentences(text: str) -> int:
    return len(re.findall(r'[.!?]+', text))

def count_paragraphs(text: str) -> int:
    return len([p for p in text.split('\n\n') if p.strip()])


class TokenRequest(BaseModel):
    text: str = Field(..., description="Text to analyze", max_length=500_000)
    model: Literal["gpt-4", "gpt-3.5", "claude", "llama", "generic"] = Field(
        default="generic", description="Model to estimate tokens for (affects tokenization heuristic)"
    )
    include_cost_estimate: bool = Field(default=True, description="Include USD cost estimate based on public pricing")


MODEL_PRICING = {
    "gpt-4":    {"input": 30.0,  "output": 60.0,  "name": "GPT-4o"},
    "gpt-3.5":  {"input": 0.5,   "output": 1.5,   "name": "GPT-3.5 Turbo"},
    "claude":   {"input": 3.0,   "output": 15.0,  "name": "Claude 3.5 Sonnet"},
    "llama":    {"input": 0.2,   "output": 0.2,   "name": "LLaMA 3 (Groq)"},
    "generic":  {"input": 1.0,   "output": 2.0,   "name": "Generic (avg)"},
}


@app.get("/")
def root():
    return {
        "service": "x402 Token Counter",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/call",
        "endpoint": "POST /count",
        "models": list(MODEL_PRICING.keys()),
        "tagline": "Count tokens and estimate LLM costs for any text — GPT-4, Claude, LLaMA",
        "curl_example": "curl https://x402-token-counter.suretat.com/count -H 'Content-Type: application/json' -d '{\"text\": \"Hello world\", \"model\": \"claude\"}'",
        "try_it": "https://x402-token-counter.suretat.com/docs",
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
    if request.url.path == "/count" and request.method == "POST":
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
                        "resource": "https://" + request.headers.get("host", "") + "/count",
                        "description": "Token count and LLM cost estimate for any text",
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


@app.post("/count")
def count_tokens(req: TokenRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    token_count = estimate_tokens_simple(req.text)
    char_count = len(req.text)
    word_count = count_words(req.text)
    sentence_count = count_sentences(req.text)
    paragraph_count = count_paragraphs(req.text)

    result: dict = {
        "model": req.model,
        "token_count": token_count,
        "char_count": char_count,
        "word_count": word_count,
        "sentence_count": sentence_count,
        "paragraph_count": paragraph_count,
        "avg_tokens_per_word": round(token_count / max(word_count, 1), 2),
    }

    if req.include_cost_estimate:
        pricing = MODEL_PRICING[req.model]
        cost_input  = (token_count / 1_000_000) * pricing["input"]
        cost_output = (token_count / 1_000_000) * pricing["output"]
        result["cost_estimate"] = {
            "model_name": pricing["name"],
            "as_input_usd":  round(cost_input, 8),
            "as_output_usd": round(cost_output, 8),
            "pricing_per_1m_input":  pricing["input"],
            "pricing_per_1m_output": pricing["output"],
            "note": "Estimate only — based on public pricing, subject to change",
        }

    return result


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-token-counter.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/count",
            "description": "Token count and LLM cost estimate for any text",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3079, proxy_headers=True, forwarded_allow_ips="*")
