from __future__ import annotations
import logging
import os
import time
from typing import Any

import dns.resolver
import dns.reversename
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-dns")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

VALID_TYPES = ["A", "AAAA", "MX", "TXT", "CNAME", "NS", "SOA", "PTR", "CAA", "SRV", "DKIM"]
stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 DNS Lookup", version="1.0.0")


class DNSRequest(BaseModel):
    domain: str = Field(..., description="Domain name to query (e.g. example.com)")
    record_types: list[str] = Field(
        default=["A", "MX", "TXT", "NS"],
        description=f"Record types to query: {', '.join(VALID_TYPES)}",
    )
    nameserver: str | None = Field(default=None, description="Custom DNS resolver IP (e.g. 8.8.8.8)")
    timeout: float = Field(default=5.0, ge=1, le=30, description="Query timeout in seconds")


def query_record(resolver: dns.resolver.Resolver, domain: str, rtype: str) -> list[str]:
    try:
        if rtype == "PTR":
            rev = dns.reversename.from_address(domain)
            answers = resolver.resolve(rev, "PTR")
        else:
            answers = resolver.resolve(domain, rtype)
        results = []
        for rdata in answers:
            if rtype == "MX":
                results.append({"priority": rdata.preference, "exchange": str(rdata.exchange).rstrip(".")})
            elif rtype == "SOA":
                results.append({
                    "mname": str(rdata.mname).rstrip("."),
                    "rname": str(rdata.rname).rstrip("."),
                    "serial": rdata.serial,
                    "refresh": rdata.refresh,
                    "retry": rdata.retry,
                    "expire": rdata.expire,
                    "minimum": rdata.minimum,
                })
            elif rtype == "SRV":
                results.append({
                    "priority": rdata.priority,
                    "weight": rdata.weight,
                    "port": rdata.port,
                    "target": str(rdata.target).rstrip("."),
                })
            else:
                results.append(str(rdata).strip('"'))
        return results
    except dns.resolver.NXDOMAIN:
        return []
    except dns.resolver.NoAnswer:
        return []
    except Exception as e:
        return [f"ERROR: {e}"]


@app.get("/")
def root():
    return {
        "service": "x402 DNS Lookup",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoint": "POST /lookup",
        "supported_types": VALID_TYPES,
        "tagline": "Query DNS records (A, MX, TXT, CNAME, NS, SOA...) for any domain",
        "curl_example": "curl https://x402-dns.suretat.com/lookup -H 'Content-Type: application/json' -d '{\"domain\": \"github.com\", \"record_types\": [\"A\", \"MX\", \"TXT\"]}'",
        "try_it": "https://x402-dns.suretat.com/docs",
        "docs": "/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/lookup" and request.method == "POST":
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
                        "resource": "https://" + request.headers.get("host", "") + "/lookup",
                        "description": "DNS record lookup — A, MX, TXT, CNAME...",
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


@app.post("/lookup")
def lookup(req: DNSRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    resolver = dns.resolver.Resolver()
    resolver.lifetime = req.timeout
    if req.nameserver:
        resolver.nameservers = [req.nameserver]

    types = [t.upper() for t in req.record_types if t.upper() in VALID_TYPES]
    results: dict[str, Any] = {}
    for rtype in types:
        results[rtype] = query_record(resolver, req.domain, rtype)

    return {
        "domain": req.domain,
        "nameserver": req.nameserver or resolver.nameservers[0],
        "records": results,
        "queried_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-dns.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/lookup",
            "description": "DNS record lookup",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3071, proxy_headers=True, forwarded_allow_ips="*")
