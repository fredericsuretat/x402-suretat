from __future__ import annotations
import os, time
import uvicorn
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import httpx

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Crypto Price", version="1.0.0")

COINGECKO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "USDC": "usd-coin", "SOL": "solana",
    "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano", "DOGE": "dogecoin",
    "AVAX": "avalanche-2", "DOT": "polkadot", "MATIC": "matic-network",
    "LINK": "chainlink", "UNI": "uniswap", "ATOM": "cosmos", "LTC": "litecoin",
    "BCH": "bitcoin-cash", "ALGO": "algorand", "XLM": "stellar", "VET": "vechain",
    "FIL": "filecoin", "THETA": "theta-token", "TRX": "tron", "EOS": "eos",
    "SHIB": "shiba-inu", "PEPE": "pepe", "ARB": "arbitrum", "OP": "optimism",
    "SUI": "sui", "APT": "aptos", "INJ": "injective-protocol",
}

PAID_PATHS = {"/price"}


def _make_402(host: str, endpoint: str = "/price") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "Real-time cryptocurrency price from CoinGecko",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/price" and request.method in ("POST", "GET"):
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-crypto-price.suretat.com"))
    return await call_next(request)


class PriceRequest(BaseModel):
    symbol: str
    currency: Optional[str] = "usd"


@app.get("/")
def root():
    return {"service": "x402 Crypto Price", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
            "supported": list(COINGECKO_IDS.keys()), "docs": "/docs"}


async def _fetch_price(symbol: str, currency: str) -> dict:
    symbol_upper = symbol.upper()
    coin_id = COINGECKO_IDS.get(symbol_upper)
    if not coin_id:
        return {"error": f"Unknown symbol: {symbol_upper}. Supported: {', '.join(COINGECKO_IDS.keys())}"}

    currency_lower = currency.lower()
    url = f"https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": currency_lower,
        "include_24hr_change": "true",
        "include_24hr_vol": "true",
        "include_market_cap": "true",
        "include_last_updated_at": "true",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    if coin_id not in data:
        return {"error": "No data returned from CoinGecko"}

    coin_data = data[coin_id]
    return {
        "symbol": symbol_upper,
        "coin_id": coin_id,
        "currency": currency_lower,
        "price": coin_data.get(currency_lower),
        "price_change_24h_pct": coin_data.get(f"{currency_lower}_24h_change"),
        "volume_24h": coin_data.get(f"{currency_lower}_24h_vol"),
        "market_cap": coin_data.get(f"{currency_lower}_market_cap"),
        "last_updated": coin_data.get("last_updated_at"),
        "source": "CoinGecko",
    }


@app.post("/price")
async def price_post(req: PriceRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    try:
        return await _fetch_price(req.symbol, req.currency or "usd")
    except httpx.HTTPError as e:
        return JSONResponse(status_code=502, content={"error": f"CoinGecko API error: {str(e)}"})


@app.get("/price")
async def price_get(
    symbol: str = Query(..., description="Crypto symbol e.g. BTC"),
    currency: str = Query("usd", description="Fiat currency e.g. eur, usd, gbp"),
):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    try:
        return await _fetch_price(symbol, currency)
    except httpx.HTTPError as e:
        return JSONResponse(status_code=502, content={"error": f"CoinGecko API error: {str(e)}"})


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-crypto-price.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/price",
        "description": "Real-time cryptocurrency price from CoinGecko",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3109, proxy_headers=True, forwarded_allow_ips="*")
