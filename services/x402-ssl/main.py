from __future__ import annotations
import logging
import os
import socket
import ssl
import time
from datetime import datetime, timezone

import uvicorn
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-ssl")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 SSL Certificate Checker", version="1.0.0")


class SSLRequest(BaseModel):
    domain: str = Field(..., description="Domain to check (e.g. example.com)")
    port: int = Field(default=443, ge=1, le=65535, description="Port to connect to")
    timeout: float = Field(default=10.0, ge=1.0, le=30.0, description="Connection timeout in seconds")
    check_chain: bool = Field(default=False, description="Return full certificate chain info")


@app.get("/")
def root():
    return {
        "service": "x402 SSL Certificate Checker",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoint": "POST /check",
        "tagline": "Check SSL certificate expiry, issuer, SANs, TLS version for any domain",
        "curl_example": "curl https://x402-ssl.suretat.com/check -H 'Content-Type: application/json' -d '{\"domain\": \"github.com\"}'",
        "try_it": "https://x402-ssl.suretat.com/docs",
        "docs": "/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/check" and request.method == "POST":
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
                        "resource": "https://" + request.headers.get("host", "") + "/check",
                        "description": "SSL certificate info — expiry, issuer, SANs, TLS version",
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


def parse_cert(cert_der: bytes) -> dict:
    cert = x509.load_der_x509_certificate(cert_der, default_backend())
    now = datetime.now(timezone.utc)

    try:
        san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        sans = san_ext.value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        sans = []

    days_left = (cert.not_valid_after_utc - now).days if hasattr(cert, "not_valid_after_utc") else (cert.not_valid_after.replace(tzinfo=timezone.utc) - now).days

    return {
        "subject": cert.subject.rfc4514_string(),
        "issuer": cert.issuer.rfc4514_string(),
        "not_before": cert.not_valid_before.isoformat() if hasattr(cert, "not_valid_before") else cert.not_valid_before_utc.isoformat(),
        "not_after": cert.not_valid_after.isoformat() if hasattr(cert, "not_valid_after") else cert.not_valid_after_utc.isoformat(),
        "days_until_expiry": days_left,
        "expired": days_left < 0,
        "expiring_soon": 0 <= days_left <= 30,
        "serial_number": str(cert.serial_number),
        "signature_algorithm": cert.signature_algorithm_oid.dotted_string,
        "sans": sans,
        "sans_count": len(sans),
    }


@app.post("/check")
def check_ssl(req: SSLRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED

    try:
        with socket.create_connection((req.domain, req.port), timeout=req.timeout) as sock:
            with context.wrap_socket(sock, server_hostname=req.domain) as ssock:
                tls_version = ssock.version()
                cipher = ssock.cipher()
                der_cert = ssock.getpeercert(binary_form=True)
                chain = ssock.getpeercert()

        cert_info = parse_cert(der_cert)

        result = {
            "domain": req.domain,
            "port": req.port,
            "tls_version": tls_version,
            "cipher": {
                "name": cipher[0] if cipher else None,
                "protocol": cipher[1] if cipher else None,
                "bits": cipher[2] if cipher else None,
            },
            "valid": True,
            "certificate": cert_info,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        return result

    except ssl.SSLCertVerificationError as e:
        return {"domain": req.domain, "port": req.port, "valid": False, "error": f"Certificate verification failed: {e}"}
    except ssl.SSLError as e:
        return {"domain": req.domain, "port": req.port, "valid": False, "error": f"SSL error: {e}"}
    except socket.timeout:
        return JSONResponse(status_code=408, content={"error": f"Connection timed out after {req.timeout}s"})
    except socket.gaierror as e:
        return JSONResponse(status_code=502, content={"error": f"DNS resolution failed: {e}"})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-ssl.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/check",
            "description": "SSL certificate info — expiry, issuer, SANs, TLS version",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3078, proxy_headers=True, forwarded_allow_ips="*")
