from __future__ import annotations
import os, time, ssl, socket
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Cert Info", version="1.0.0")


def _make_402(host: str, endpoint: str = "/check") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "SSL/TLS certificate inspection and analysis",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/check" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-cert-info.suretat.com"))
    return await call_next(request)


class CheckRequest(BaseModel):
    hostname: str
    port: Optional[int] = 443
    timeout: Optional[int] = 10


def _grade_cert(days_remaining: int, is_expired: bool, has_san: bool) -> str:
    if is_expired:
        return "F"
    if days_remaining < 7:
        return "C"
    if days_remaining < 30:
        return "B"
    if has_san:
        return "A"
    return "B"


@app.get("/")
def root():
    return {"service": "x402 Cert Info", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/check")
def check(req: CheckRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    hostname = req.hostname.strip().lower()
    if hostname.startswith("https://"):
        hostname = hostname[8:]
    if hostname.startswith("http://"):
        hostname = hostname[7:]
    hostname = hostname.split("/")[0]

    port = req.port or 443

    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=req.timeout or 10) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                tls_version = ssock.version()
                cipher = ssock.cipher()
    except ssl.SSLCertVerificationError as e:
        # Try without verification to still get cert info
        try:
            ctx2 = ssl.create_default_context()
            ctx2.check_hostname = False
            ctx2.verify_mode = ssl.CERT_NONE
            with socket.create_connection((hostname, port), timeout=req.timeout or 10) as sock:
                with ctx2.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    tls_version = ssock.version()
                    cipher = ssock.cipher()
        except Exception as e2:
            return JSONResponse(status_code=502, content={"error": f"Connection failed: {str(e2)}"})
    except (socket.timeout, socket.gaierror, ConnectionRefusedError) as e:
        return JSONResponse(status_code=502, content={"error": f"Connection failed: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})

    # Parse dates
    fmt = "%b %d %H:%M:%S %Y %Z"
    not_before_str = cert.get("notBefore", "")
    not_after_str = cert.get("notAfter", "")

    try:
        valid_from = datetime.strptime(not_before_str, fmt).replace(tzinfo=timezone.utc)
        valid_to = datetime.strptime(not_after_str, fmt).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        days_remaining = (valid_to - now).days
        is_expired = days_remaining < 0
    except Exception:
        valid_from = None
        valid_to = None
        days_remaining = None
        is_expired = None

    # Subject and issuer
    subject = dict(x[0] for x in cert.get("subject", []))
    issuer = dict(x[0] for x in cert.get("issuer", []))

    # SANs
    san_list = []
    for san_type, san_val in cert.get("subjectAltName", []):
        san_list.append(f"{san_type}:{san_val}")

    grade = _grade_cert(days_remaining or 0, bool(is_expired), bool(san_list))

    return {
        "hostname": hostname,
        "port": port,
        "subject": subject,
        "issuer": issuer,
        "valid_from": str(valid_from) if valid_from else None,
        "valid_to": str(valid_to) if valid_to else None,
        "days_remaining": days_remaining,
        "is_expired": is_expired,
        "sans": san_list,
        "sans_count": len(san_list),
        "tls_version": tls_version,
        "cipher": cipher[0] if cipher else None,
        "serial_number": str(cert.get("serialNumber", "")),
        "grade": grade,
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-cert-info.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/check",
        "description": "SSL/TLS certificate inspection and analysis",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3103, proxy_headers=True, forwarded_allow_ips="*")
