import os
import json
import uuid
import re
from datetime import datetime
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
USDC_ADDRESS = os.getenv("USDC_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
NETWORK = os.getenv("NETWORK", "base")

app = FastAPI(title="x402 UUID Generator", version="1.0.0")

PAYMENT_INFO = {
    "x402Version": 1,
    "accepts": [{
        "scheme": "exact",
        "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"http://{os.getenv('HOST', 'localhost')}:{os.getenv('PORT', '3067')}/generate",
        "description": "UUID Generator / Validator",
        "mimeType": "application/json",
        "payTo": PAY_TO,
        "maxTimeoutSeconds": 300,
        "asset": USDC_ADDRESS,
        "extra": {"name": "USD Coin", "version": "2"}
    }]
}

def verify_payment(request: Request) -> bool:
    return bool(request.headers.get("X-PAYMENT") or request.headers.get("x-payment", ""))

UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-([0-9a-f])[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)

def uuid_info(u: uuid.UUID) -> dict:
    info = {
        "uuid": str(u),
        "urn": u.urn,
        "hex": u.hex,
        "int": u.int,
        "version": u.version if u.version else "N/A",
        "variant": str(u.variant),
        "bytes": list(u.bytes),
    }
    if u.version == 1:
        # UUID v1 contains timestamp
        ts_100ns = (u.int >> 64) & 0x0FFFFFFFFFFFFFFF
        ts_us = ts_100ns / 10
        # UUID epoch: 15 Oct 1582
        from datetime import timedelta
        uuid_epoch = datetime(1582, 10, 15)
        ts = uuid_epoch + timedelta(microseconds=ts_us)
        info["timestamp_utc"] = ts.isoformat() + "Z"
        info["node"] = hex(u.node)
        info["clock_seq"] = u.clock_seq
    elif u.version == 4:
        info["note"] = "UUID v4 — généré aléatoirement, aucune info temporelle"
    elif u.version == 5:
        info["note"] = "UUID v5 — basé sur SHA-1 d'un nom dans un namespace"
    elif u.version == 3:
        info["note"] = "UUID v3 — basé sur MD5 d'un nom dans un namespace"
    return info

NAMESPACES = {
    "dns": uuid.NAMESPACE_DNS,
    "url": uuid.NAMESPACE_URL,
    "oid": uuid.NAMESPACE_OID,
    "x500": uuid.NAMESPACE_X500,
}

class GenerateRequest(BaseModel):
    version: int = Field(default=4, ge=1, le=5, description="Version: 1, 3, 4, 5")
    count: int = Field(default=1, ge=1, le=50)
    namespace: str = Field(default="dns", description="Pour v3/v5: dns, url, oid, x500")
    name: str = Field(default="example.com", description="Pour v3/v5: nom à hasher")
    upper: bool = Field(default=False)

class ValidateRequest(BaseModel):
    uuid_str: str

class ConvertRequest(BaseModel):
    uuid_str: str

@app.get("/")
def info():
    return {
        "service": "x402 UUID Generator",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoints": ["POST /generate", "POST /validate", "POST /convert"],
        "versions_supportees": [1, 3, 4, 5],
        "docs": "/docs",
        "tagline": "Generate UUID v1/v3/v4/v5, validate and convert between formats",
        "curl_example": "curl https://x402-uuid.suretat.com/generate -H 'Content-Type: application/json' -d '{\"version\": 4, \"count\": 5}'",
        "try_it": "https://x402-uuid.suretat.com/docs",
    }

@app.post("/generate")
async def generate(req: Request, body: GenerateRequest):
    if not verify_payment(req):
        return Response(content=json.dumps({"error": "Payment required", "x402": PAYMENT_INFO}),
                        status_code=402, media_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-ACCEPTS-PAYMENT": "x402"})
    results = []
    ns = NAMESPACES.get(body.namespace.lower(), uuid.NAMESPACE_DNS)

    for _ in range(body.count):
        if body.version == 1:
            u = uuid.uuid1()
        elif body.version == 3:
            u = uuid.uuid3(ns, body.name)
        elif body.version == 4:
            u = uuid.uuid4()
        elif body.version == 5:
            u = uuid.uuid5(ns, body.name)
        else:
            return {"error": f"Version {body.version} non supportée"}

        s = str(u).upper() if body.upper else str(u)
        results.append(s)

    if body.count == 1:
        u_obj = uuid.UUID(results[0])
        return uuid_info(u_obj) | {"uuid": results[0]}
    return {"count": body.count, "version": body.version, "uuids": results}

@app.post("/validate")
async def validate(req: Request, body: ValidateRequest):
    if not verify_payment(req):
        return Response(content=json.dumps({"error": "Payment required", "x402": PAYMENT_INFO}),
                        status_code=402, media_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-ACCEPTS-PAYMENT": "x402"})
    s = body.uuid_str.strip()
    if not UUID_RE.match(s):
        # Try with or without braces
        s = s.strip("{}")
        if not UUID_RE.match(s):
            return {"valide": False, "erreur": "Format UUID invalide", "entree": body.uuid_str}
    try:
        u = uuid.UUID(s)
        return {"valide": True} | uuid_info(u)
    except ValueError as e:
        return {"valide": False, "erreur": str(e)}

@app.post("/convert")
async def convert(req: Request, body: ConvertRequest):
    if not verify_payment(req):
        return Response(content=json.dumps({"error": "Payment required", "x402": PAYMENT_INFO}),
                        status_code=402, media_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-ACCEPTS-PAYMENT": "x402"})
    s = body.uuid_str.strip().strip("{}")
    # Accept hex without dashes, int, or standard format
    try:
        if s.isdigit():
            u = uuid.UUID(int=int(s))
        elif len(s) == 32 and all(c in "0123456789abcdefABCDEF" for c in s):
            u = uuid.UUID(hex=s)
        else:
            u = uuid.UUID(s)
    except ValueError as e:
        return {"error": f"Impossible de parser: {e}"}
    return {
        "standard": str(u),
        "upper": str(u).upper(),
        "hex": u.hex,
        "braces": "{" + str(u) + "}",
        "urn": u.urn,
        "integer": u.int,
        "base64url": __import__("base64").urlsafe_b64encode(u.bytes).decode().rstrip("="),
        "bytes_hex": u.bytes.hex(),
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
            "description": "x402 UUID Generator",
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

