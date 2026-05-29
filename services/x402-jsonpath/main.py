from __future__ import annotations
import os, time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any
from jsonpath_ng import parse as jsonpath_parse

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 JSONPath", version="1.0.0")


def _make_402(host: str, endpoint: str = "/query") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "JSONPath query on any JSON document",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/query" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-jsonpath.suretat.com"))
    return await call_next(request)


class QueryRequest(BaseModel):
    json: Any
    path: str


@app.get("/")
def root():
    return {"service": "x402 JSONPath", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/query")
def query(req: QueryRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        expr = jsonpath_parse(req.path)
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Invalid JSONPath expression: {str(e)}"})

    try:
        matches = expr.find(req.json)
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Query failed: {str(e)}"})

    results = [m.value for m in matches]
    paths = [str(m.full_path) for m in matches]

    return {
        "results": results,
        "paths": paths,
        "count": len(results),
        "path": req.path,
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-jsonpath.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/query",
        "description": "JSONPath query on any JSON document", "mimeType": "application/json",
        "payTo": PAY_TO, "maxTimeoutSeconds": 300, "asset": ASSET_ADDRESS,
        "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3095, proxy_headers=True, forwarded_allow_ips="*")
