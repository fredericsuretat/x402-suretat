from __future__ import annotations
import difflib
import logging
import os
import time
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-diff")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Text Diff", version="1.0.0")


class DiffRequest(BaseModel):
    text1: str = Field(..., description="Original text", max_length=500_000)
    text2: str = Field(..., description="Modified text", max_length=500_000)
    format: Literal["unified", "html", "ndiff", "summary"] = Field(
        default="unified",
        description="Output format: unified (patch), html (colored), ndiff (line-by-line), summary (stats only)",
    )
    context_lines: int = Field(default=3, ge=0, le=20, description="Lines of context around changes (unified only)")
    fromfile: str = Field(default="original", description="Label for the original file")
    tofile: str = Field(default="modified", description="Label for the modified file")


@app.get("/")
def root():
    return {
        "service": "x402 Text Diff",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoint": "POST /diff",
        "tagline": "Compute unified diff, HTML diff or line-by-line diff between two texts",
        "curl_example": "curl https://x402-diff.suretat.com/diff -H 'Content-Type: application/json' -d '{\"text1\": \"hello world\", \"text2\": \"hello claude\", \"format\": \"unified\"}'",
        "try_it": "https://x402-diff.suretat.com/docs",
        "docs": "/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/diff" and request.method == "POST":
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
                        "resource": "https://" + request.headers.get("host", "") + "/diff",
                        "description": "Text diff — unified, HTML, ndiff",
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


@app.post("/diff")
def compute_diff(req: DiffRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    lines1 = req.text1.splitlines(keepends=True)
    lines2 = req.text2.splitlines(keepends=True)

    # Stats always computed
    sm = difflib.SequenceMatcher(None, lines1, lines2)
    ratio = sm.ratio()
    opcodes = sm.get_opcodes()
    additions = sum(j2 - j1 for tag, _, _, j1, j2 in opcodes if tag in ("insert", "replace"))
    deletions = sum(i2 - i1 for tag, i1, i2, _, _ in opcodes if tag in ("delete", "replace"))
    changes = sum(1 for tag, *_ in opcodes if tag != "equal")

    result: dict = {
        "similarity": round(ratio, 4),
        "additions": additions,
        "deletions": deletions,
        "change_blocks": changes,
        "total_lines_original": len(lines1),
        "total_lines_modified": len(lines2),
    }

    if req.format == "summary":
        return result

    if req.format == "unified":
        diff = "".join(difflib.unified_diff(
            lines1, lines2,
            fromfile=req.fromfile,
            tofile=req.tofile,
            n=req.context_lines,
        ))
        result["diff"] = diff

    elif req.format == "html":
        diff_html = difflib.HtmlDiff().make_file(
            lines1, lines2,
            fromdesc=req.fromfile,
            todesc=req.tofile,
            context=True,
            numlines=req.context_lines,
        )
        result["html"] = diff_html

    elif req.format == "ndiff":
        diff = "".join(difflib.ndiff(lines1, lines2))
        result["diff"] = diff

    return result


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-diff.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/diff",
            "description": "Text diff — unified, HTML, ndiff",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3072, proxy_headers=True, forwarded_allow_ips="*")
