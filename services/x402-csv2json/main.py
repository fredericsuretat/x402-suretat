from __future__ import annotations
import csv
import io
import json
import logging
import os
import time
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-csv2json")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 CSV ↔ JSON", version="1.0.0")


class Csv2JsonRequest(BaseModel):
    csv: str = Field(..., description="CSV content as string", max_length=5_000_000)
    delimiter: str = Field(default=",", description="Field delimiter (default: comma)")
    has_header: bool = Field(default=True, description="First row is a header")
    skip_empty: bool = Field(default=True, description="Skip empty rows")
    cast_numbers: bool = Field(default=True, description="Auto-cast numeric strings to numbers")


class Json2CsvRequest(BaseModel):
    data: list[dict[str, Any]] = Field(..., description="Array of objects to convert to CSV")
    delimiter: str = Field(default=",", description="Field delimiter")
    include_header: bool = Field(default=True, description="Include header row")
    fieldnames: list[str] | None = Field(default=None, description="Column order (defaults to keys of first object)")


def try_cast(value: str, cast: bool) -> Any:
    if not cast:
        return value
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value


@app.get("/")
def root():
    return {
        "service": "x402 CSV <-> JSON",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoints": ["POST /csv2json", "POST /json2csv"],
        "tagline": "Convert CSV to JSON array of objects, or JSON array back to CSV — with auto-typing",
        "curl_example": "curl https://x402-csv2json.suretat.com/csv2json -H 'Content-Type: application/json' -d '{\"csv\": \"name,age\\nAlice,30\\nBob,25\"}'",
        "try_it": "https://x402-csv2json.suretat.com/docs",
        "docs": "/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


PAID_PATHS = {"/csv2json", "/json2csv"}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path in PAID_PATHS and request.method == "POST":
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
                        "resource": "https://" + request.headers.get("host", "") + request.url.path,
                        "description": "CSV <-> JSON conversion",
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


@app.post("/csv2json")
def csv_to_json(req: Csv2JsonRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    reader = csv.DictReader(
        io.StringIO(req.csv),
        delimiter=req.delimiter,
    ) if req.has_header else csv.reader(io.StringIO(req.csv), delimiter=req.delimiter)

    rows = []
    headers: list[str] = []

    if req.has_header:
        for row in reader:
            if req.skip_empty and not any(row.values()):
                continue
            rows.append({k: try_cast(v, req.cast_numbers) for k, v in row.items()})
        headers = list(reader.fieldnames or [])
    else:
        raw_rows = list(reader)
        if raw_rows:
            headers = [f"col{i}" for i in range(len(raw_rows[0]))]
        for row in raw_rows:
            if req.skip_empty and not any(row):
                continue
            rows.append({f"col{i}": try_cast(v, req.cast_numbers) for i, v in enumerate(row)})

    return {"headers": headers, "rows": rows, "count": len(rows)}


@app.post("/json2csv")
def json_to_csv(req: Json2CsvRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if not req.data:
        return {"csv": "", "rows": 0}

    fieldnames = req.fieldnames or list(req.data[0].keys())
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, delimiter=req.delimiter, extrasaction="ignore")
    if req.include_header:
        writer.writeheader()
    writer.writerows(req.data)

    return {"csv": out.getvalue(), "rows": len(req.data), "columns": fieldnames}


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-csv2json.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/csv2json",
            "description": "CSV <-> JSON conversion",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3073, proxy_headers=True, forwarded_allow_ips="*")
