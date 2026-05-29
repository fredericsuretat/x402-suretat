from __future__ import annotations
import os, time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import yaml
import json

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 YAML2JSON", version="1.0.0")


def _make_402(host: str, endpoint: str = "/convert") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "Bidirectional YAML<->JSON conversion",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/convert" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-yaml2json.suretat.com"))
    return await call_next(request)


class ConvertRequest(BaseModel):
    input: str
    to: str  # "json" or "yaml"


@app.get("/")
def root():
    return {"service": "x402 YAML2JSON", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/convert")
def convert(req: ConvertRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    target = req.to.lower()
    if target not in ("json", "yaml"):
        return JSONResponse(status_code=400, content={"error": "to must be 'json' or 'yaml'"})

    # Try to parse input as JSON first, then as YAML
    parsed = None
    input_format = None
    try:
        parsed = json.loads(req.input)
        input_format = "json"
    except (json.JSONDecodeError, ValueError):
        pass

    if parsed is None:
        try:
            parsed = yaml.safe_load(req.input)
            input_format = "yaml"
        except yaml.YAMLError as e:
            return JSONResponse(status_code=422, content={"error": f"Failed to parse input: {str(e)}"})

    if parsed is None:
        return JSONResponse(status_code=422, content={"error": "Input is null or empty"})

    if target == "json":
        result = json.dumps(parsed, indent=2, ensure_ascii=False)
    else:
        result = yaml.dump(parsed, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return {
        "output": result,
        "input_format": input_format,
        "output_format": target,
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-yaml2json.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/convert",
        "description": "Bidirectional YAML<->JSON conversion", "mimeType": "application/json",
        "payTo": PAY_TO, "maxTimeoutSeconds": 300, "asset": ASSET_ADDRESS,
        "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3094, proxy_headers=True, forwarded_allow_ips="*")
