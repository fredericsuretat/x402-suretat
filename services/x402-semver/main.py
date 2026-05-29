from __future__ import annotations
import os, time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import semver

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Semver", version="1.0.0")

PAID_PATHS = {"/parse", "/compare", "/increment", "/satisfies"}


def _make_402(host: str, endpoint: str = "/parse") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "Semantic version parsing, comparison and manipulation",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path in PAID_PATHS and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-semver.suretat.com"), request.url.path)
    return await call_next(request)


class ParseRequest(BaseModel):
    version: str


class CompareRequest(BaseModel):
    version1: str
    version2: str


class IncrementRequest(BaseModel):
    version: str
    part: str  # major, minor, patch, prerelease
    prerelease_token: Optional[str] = "rc"


class SatisfiesRequest(BaseModel):
    version: str
    range: str


@app.get("/")
def root():
    return {"service": "x402 Semver", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/parse")
def parse(req: ParseRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    try:
        v = semver.Version.parse(req.version)
        return {
            "version": str(v),
            "major": v.major,
            "minor": v.minor,
            "patch": v.patch,
            "prerelease": v.prerelease,
            "build": v.build,
            "is_prerelease": v.prerelease is not None,
        }
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})


@app.post("/compare")
def compare(req: CompareRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    try:
        v1 = semver.Version.parse(req.version1)
        v2 = semver.Version.parse(req.version2)
        cmp = v1.compare(v2)
        return {
            "version1": str(v1),
            "version2": str(v2),
            "result": cmp,  # -1, 0, 1
            "relation": "less_than" if cmp < 0 else ("equal" if cmp == 0 else "greater_than"),
            "is_equal": cmp == 0,
            "v1_is_newer": cmp > 0,
        }
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})


@app.post("/increment")
def increment(req: IncrementRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    try:
        v = semver.Version.parse(req.version)
        part = req.part.lower()
        if part == "major":
            result = v.bump_major()
        elif part == "minor":
            result = v.bump_minor()
        elif part == "patch":
            result = v.bump_patch()
        elif part == "prerelease":
            result = v.bump_prerelease(token=req.prerelease_token or "rc")
        else:
            return JSONResponse(status_code=400, content={"error": "part must be major, minor, patch or prerelease"})
        return {"original": str(v), "incremented": str(result), "part": part}
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})


@app.post("/satisfies")
def satisfies(req: SatisfiesRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    try:
        v = semver.Version.parse(req.version)
        # Parse range manually: supports >=X.Y.Z <X.Y.Z and ==X.Y.Z
        range_str = req.range.strip()
        result = _check_range(v, range_str)
        return {"version": str(v), "range": range_str, "satisfies": result}
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})


def _check_range(v: semver.Version, range_str: str) -> bool:
    parts = range_str.split()
    results = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        for op in (">=", "<=", "!=", ">", "<", "==", "=", "^", "~"):
            if part.startswith(op):
                ver_str = part[len(op):]
                try:
                    other = semver.Version.parse(ver_str)
                except ValueError:
                    results.append(False)
                    break
                cmp = v.compare(other)
                if op in (">=",):
                    results.append(cmp >= 0)
                elif op in ("<=",):
                    results.append(cmp <= 0)
                elif op in (">",):
                    results.append(cmp > 0)
                elif op in ("<",):
                    results.append(cmp < 0)
                elif op in ("==", "="):
                    results.append(cmp == 0)
                elif op == "!=":
                    results.append(cmp != 0)
                elif op == "^":
                    # Compatible with: same major
                    results.append(v.major == other.major and v.compare(other) >= 0)
                elif op == "~":
                    # Approximately: same major.minor
                    results.append(v.major == other.major and v.minor == other.minor and v.compare(other) >= 0)
                break
        else:
            try:
                other = semver.Version.parse(part)
                results.append(v.compare(other) == 0)
            except ValueError:
                results.append(False)
    return all(results) if results else False


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-semver.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/parse",
        "description": "Semantic version parsing, comparison and manipulation",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3098, proxy_headers=True, forwarded_allow_ips="*")
