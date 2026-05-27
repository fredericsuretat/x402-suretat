from __future__ import annotations
import ipaddress
import logging
import os
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-subnet")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Subnet Calculator", version="1.0.0")


class SubnetRequest(BaseModel):
    cidr: str = Field(..., description="Réseau CIDR (ex: 192.168.1.0/24 ou 192.168.1.50/24)", examples=["192.168.1.0/24"])
    subnets: int | None = Field(default=None, ge=2, le=65536, description="Diviser en N sous-réseaux (optionnel)")


class CheckIPRequest(BaseModel):
    ip: str = Field(..., description="Adresse IP à vérifier")
    cidr: str = Field(..., description="Réseau CIDR de référence")


@app.get("/")
def root():
    return {
        "service": "x402 Subnet Calculator",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/calcul",
        "endpoints": {
            "POST /calculate": "Informations réseau CIDR",
            "POST /check": "Vérifier si une IP appartient à un réseau",
        },
        "docs": "/docs",
        "tagline": "Calculate network, broadcast and hosts from any CIDR notation",
        "curl_example": "curl https://x402-subnet.suretat.com/calculate -H 'Content-Type: application/json' -d '{\"cidr\": \"192.168.1.0/24\"}'",
        "try_it": "https://x402-subnet.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path in ("/calculate", "/check") and request.method == "POST":
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
                        "resource": "https://" + request.headers.get("host", str(request.url.hostname)) + str(request.url.path),
                        "description": "Subnet calculation — 0.0005 USDC",
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


@app.post("/calculate")
def calculate_subnet(req: SubnetRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        net = ipaddress.ip_network(req.cidr, strict=False)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e), "cidr": req.cidr})

    is_v6 = isinstance(net, ipaddress.IPv6Network)
    total_hosts = net.num_addresses - 2 if net.prefixlen < (128 if is_v6 else 32) else net.num_addresses

    result: dict = {
        "cidr": str(net),
        "version": 6 if is_v6 else 4,
        "adresse_reseau": str(net.network_address),
        "adresse_broadcast": str(net.broadcast_address) if not is_v6 else None,
        "masque_sous_reseau": str(net.netmask) if not is_v6 else None,
        "masque_wildcard": str(net.hostmask) if not is_v6 else None,
        "prefixe": net.prefixlen,
        "total_adresses": net.num_addresses,
        "hotes_utilisables": max(0, total_hosts),
        "premiere_ip_utilisable": str(net.network_address + 1) if not is_v6 and net.prefixlen < 32 else None,
        "derniere_ip_utilisable": str(net.broadcast_address - 1) if not is_v6 and net.prefixlen < 31 else None,
        "type": (
            "Privé" if net.is_private else
            "Loopback" if net.is_loopback else
            "Lien local" if net.is_link_local else
            "Multicast" if net.is_multicast else
            "Public"
        ),
    }

    if req.subnets and not is_v6:
        import math
        bits_needed = math.ceil(math.log2(req.subnets))
        new_prefix = net.prefixlen + bits_needed
        if new_prefix <= 30:
            subnets_list = list(net.subnets(prefixlen_diff=bits_needed))[:req.subnets]
            result["sous_reseaux"] = [
                {
                    "cidr": str(s),
                    "reseau": str(s.network_address),
                    "broadcast": str(s.broadcast_address),
                    "hotes": s.num_addresses - 2,
                }
                for s in subnets_list
            ]
        else:
            result["sous_reseaux_erreur"] = f"Impossible: préfixe /{new_prefix} dépasserait /30"

    return result


@app.post("/check")
def check_ip_in_network(req: CheckIPRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        ip = ipaddress.ip_address(req.ip)
        net = ipaddress.ip_network(req.cidr, strict=False)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

    appartient = ip in net
    return {
        "ip": str(ip),
        "reseau": str(net),
        "appartient_au_reseau": appartient,
        "est_adresse_reseau": ip == net.network_address,
        "est_broadcast": hasattr(net, "broadcast_address") and ip == net.broadcast_address,
        "est_utilisable": appartient and ip != net.network_address and (not hasattr(net, "broadcast_address") or ip != net.broadcast_address),
    }



@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK if "NETWORK" in dir() else os.getenv("NETWORK", "base"),
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/api",
            "description": "x402 Subnet Calculator",
            "mimeType": "application/json",
            "payTo": PAY_TO if "PAY_TO" in dir() else os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b"),
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS if "ASSET_ADDRESS" in dir() else "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "extra": {"name": "USDC", "version": "2"},
        }]
    }

@app.get("/.well-known/x402")
async def x402_well_known_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/.well-known/x402.json")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3053)
