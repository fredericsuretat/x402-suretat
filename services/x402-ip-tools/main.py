from __future__ import annotations
import ipaddress
import logging
import os
import re
import socket
import time
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-ip-tools")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 IP Tools", version="1.0.0")

PAID_PATHS = {"/analyze", "/range", "/rdns"}


def analyze_ip(ip_str: str) -> dict:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError as e:
        return {"error": str(e)}

    version = ip.version
    result: dict = {
        "ip": str(ip),
        "version": f"IPv{version}",
        "is_private": ip.is_private,
        "is_global": ip.is_global,
        "is_loopback": ip.is_loopback,
        "is_multicast": ip.is_multicast,
        "is_link_local": ip.is_link_local,
        "is_reserved": ip.is_reserved,
        "is_unspecified": ip.is_unspecified,
    }

    if version == 4:
        result["packed_int"] = int(ip)
        result["binary"] = format(int(ip), "032b")
        result["hex"] = format(int(ip), "08x")
        # Classify classful network (legacy)
        first_octet = int(str(ip).split(".")[0])
        if first_octet < 128:
            result["classful_class"] = "A"
        elif first_octet < 192:
            result["classful_class"] = "B"
        elif first_octet < 224:
            result["classful_class"] = "C"
        elif first_octet < 240:
            result["classful_class"] = "D (multicast)"
        else:
            result["classful_class"] = "E (reserved)"
    else:
        result["expanded"] = str(ip.exploded)
        result["compressed"] = str(ip.compressed)
        result["ipv4_mapped"] = str(ip.ipv4_mapped) if ip.ipv4_mapped else None
        result["is_ipv4_mapped"] = ip.ipv4_mapped is not None

    return result


def analyze_cidr(cidr_str: str) -> dict:
    try:
        net = ipaddress.ip_network(cidr_str, strict=False)
    except ValueError as e:
        return {"error": str(e)}

    hosts = list(net.hosts())
    return {
        "network": str(net.network_address),
        "broadcast": str(net.broadcast_address) if net.version == 4 else None,
        "netmask": str(net.netmask) if net.version == 4 else None,
        "prefix_length": net.prefixlen,
        "version": f"IPv{net.version}",
        "total_addresses": net.num_addresses,
        "usable_hosts": len(hosts),
        "first_host": str(hosts[0]) if hosts else None,
        "last_host": str(hosts[-1]) if hosts else None,
        "is_private": net.is_private,
        "is_global": net.is_global,
        "supernet": str(net.supernet()),
    }


class IPAnalyzeRequest(BaseModel):
    ip: str = Field(..., description="IPv4 or IPv6 address to analyze")
    reverse_dns: bool = Field(default=False, description="Perform reverse DNS lookup")


class CIDRRequest(BaseModel):
    cidr: str = Field(..., description="CIDR notation (e.g. 192.168.1.0/24)")


class RDNSRequest(BaseModel):
    ip: str = Field(..., description="IP address for reverse DNS lookup")
    timeout: float = Field(default=5.0, ge=1.0, le=15.0)


@app.get("/")
def root():
    return {
        "service": "x402 IP Tools",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/call",
        "endpoints": ["POST /analyze", "POST /range", "POST /rdns"],
        "tagline": "IP address analysis — type, class, CIDR range, reverse DNS — IPv4 and IPv6",
        "curl_example": "curl https://x402-ip-tools.suretat.com/analyze -H 'Content-Type: application/json' -d '{\"ip\": \"8.8.8.8\"}'",
        "try_it": "https://x402-ip-tools.suretat.com/docs",
        "docs": "/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


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
                        "description": "IP analysis — type, class, CIDR, reverse DNS",
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


@app.post("/analyze")
def analyze(req: IPAnalyzeRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    result = analyze_ip(req.ip)
    if req.reverse_dns and "error" not in result:
        try:
            rdns = socket.gethostbyaddr(req.ip)
            result["rdns"] = {"hostname": rdns[0], "aliases": rdns[1]}
        except Exception as e:
            result["rdns"] = {"error": str(e)}
    return result


@app.post("/range")
def cidr_range(req: CIDRRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    return analyze_cidr(req.cidr)


@app.post("/rdns")
def reverse_dns(req: RDNSRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    try:
        socket.setdefaulttimeout(req.timeout)
        rdns = socket.gethostbyaddr(req.ip)
        return {"ip": req.ip, "hostname": rdns[0], "aliases": rdns[1], "addresses": rdns[2]}
    except socket.herror as e:
        return JSONResponse(status_code=404, content={"error": f"No reverse DNS: {e}"})
    except socket.timeout:
        return JSONResponse(status_code=408, content={"error": "DNS timeout"})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-ip-tools.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/analyze",
            "description": "IP analysis — type, class, CIDR, reverse DNS",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3083, proxy_headers=True, forwarded_allow_ips="*")
