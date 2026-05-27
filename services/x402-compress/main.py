from __future__ import annotations
import base64
import brotli
import gzip
import io
import logging
import os
import time
import zlib
import zipfile
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-compress")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
MAX_SIZE_MB   = int(os.getenv("MAX_SIZE_MB", "10"))

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Compress / Decompress", version="1.0.0")

Algorithm = Literal["gzip", "zlib", "brotli", "zip"]


class CompressRequest(BaseModel):
    data: str = Field(..., description="Data to compress (UTF-8 string or base64-encoded binary)")
    algorithm: Algorithm = Field(default="gzip", description="Compression algorithm")
    level: int = Field(default=6, ge=1, le=9, description="Compression level (1=fast, 9=best)")
    input_encoding: Literal["utf8", "base64"] = Field(default="utf8", description="Input encoding")
    filename: str | None = Field(default=None, description="Filename hint (used for zip archives)")


class DecompressRequest(BaseModel):
    data_base64: str = Field(..., description="Base64-encoded compressed data")
    algorithm: Algorithm = Field(default="gzip", description="Compression algorithm to decompress")
    output_encoding: Literal["utf8", "base64"] = Field(default="utf8", description="Output encoding")


@app.get("/")
def root():
    return {
        "service": "x402 Compress / Decompress",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoints": ["POST /compress", "POST /decompress"],
        "algorithms": ["gzip", "zlib", "brotli", "zip"],
        "tagline": "Compress or decompress data with gzip, zlib, brotli or zip — returns base64",
        "curl_example": "curl https://x402-compress.suretat.com/compress -H 'Content-Type: application/json' -d '{\"data\": \"Hello World! This is a test string.\", \"algorithm\": \"gzip\"}'",
        "try_it": "https://x402-compress.suretat.com/docs",
        "docs": "/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


PAID_PATHS = {"/compress", "/decompress"}


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
                        "description": "Compress/decompress gzip, zlib, brotli, zip",
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


@app.post("/compress")
def compress(req: CompressRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        if req.input_encoding == "base64":
            raw = base64.b64decode(req.data)
        else:
            raw = req.data.encode("utf-8")
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Input decode error: {e}"})

    if len(raw) > MAX_SIZE_MB * 1024 * 1024:
        return JSONResponse(status_code=413, content={"error": f"Input too large (max {MAX_SIZE_MB} MB)"})

    try:
        if req.algorithm == "gzip":
            compressed = gzip.compress(raw, compresslevel=req.level)
        elif req.algorithm == "zlib":
            compressed = zlib.compress(raw, level=req.level)
        elif req.algorithm == "brotli":
            compressed = brotli.compress(raw, quality=req.level)
        elif req.algorithm == "zip":
            buf = io.BytesIO()
            fname = req.filename or "data.bin"
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=req.level) as zf:
                zf.writestr(fname, raw)
            compressed = buf.getvalue()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Compression error: {e}"})

    ratio = round(len(compressed) / max(len(raw), 1) * 100, 1)
    return {
        "algorithm": req.algorithm,
        "original_bytes": len(raw),
        "compressed_bytes": len(compressed),
        "ratio_pct": ratio,
        "savings_pct": round(100 - ratio, 1),
        "compressed_base64": base64.b64encode(compressed).decode(),
    }


@app.post("/decompress")
def decompress(req: DecompressRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        compressed = base64.b64decode(req.data_base64)
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Base64 decode error: {e}"})

    try:
        if req.algorithm == "gzip":
            raw = gzip.decompress(compressed)
        elif req.algorithm == "zlib":
            raw = zlib.decompress(compressed)
        elif req.algorithm == "brotli":
            raw = brotli.decompress(compressed)
        elif req.algorithm == "zip":
            buf = io.BytesIO(compressed)
            with zipfile.ZipFile(buf, "r") as zf:
                names = zf.namelist()
                raw = zf.read(names[0])
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Decompression error: {e}"})

    if req.output_encoding == "base64":
        return {"algorithm": req.algorithm, "decompressed_bytes": len(raw), "data_base64": base64.b64encode(raw).decode()}

    try:
        text = raw.decode("utf-8")
        return {"algorithm": req.algorithm, "decompressed_bytes": len(raw), "data": text}
    except UnicodeDecodeError:
        return {"algorithm": req.algorithm, "decompressed_bytes": len(raw), "data_base64": base64.b64encode(raw).decode(), "note": "Binary data, returned as base64"}


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-compress.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/compress",
            "description": "Compress/decompress gzip, zlib, brotli, zip",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3077, proxy_headers=True, forwarded_allow_ips="*")
