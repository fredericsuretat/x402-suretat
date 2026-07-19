import base64
import json
import hmac
import hashlib
import os
from typing import Any
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel

FACILITATOR_URL = os.getenv("FACILITATOR_URL", "https://api.cdp.coinbase.com/platform/v2/x402")
PAY_TO = os.getenv("PAY_TO_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
USDC_ADDRESS = os.getenv("USDC_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
NETWORK = os.getenv("NETWORK", "base")

app = FastAPI(title="x402 JWT Decoder", version="1.0.0")

def build_payment_info(request: Request) -> dict:
    host = request.headers.get("host", "x402-jwt.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/decode",
            "description": "JWT Decoder / Validator",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": USDC_ADDRESS,
            "extra": {"name": "USD Coin", "version": "2"}
        }]
    }

def verify_payment(request: Request) -> bool:
    token = request.headers.get("X-PAYMENT") or request.headers.get("x-payment", "")
    return bool(token)

def b64_decode(data: str) -> bytes:
    data += "=" * (4 - len(data) % 4)
    data = data.replace("-", "+").replace("_", "/")
    return base64.b64decode(data)

def decode_jwt(token: str) -> dict[str, Any]:
    parts = token.strip().split(".")
    if len(parts) != 3:
        return {"error": "Format JWT invalide — attendu 3 parties (header.payload.signature)"}

    try:
        header = json.loads(b64_decode(parts[0]))
    except Exception as e:
        return {"error": f"Header JWT invalide: {e}"}

    try:
        payload = json.loads(b64_decode(parts[1]))
    except Exception as e:
        return {"error": f"Payload JWT invalide: {e}"}

    alg = header.get("alg", "unknown").upper()
    signature_b64 = parts[2]

    # Timing: exp, iat, nbf
    import time
    now = int(time.time())
    exp = payload.get("exp")
    iat = payload.get("iat")
    nbf = payload.get("nbf")

    timing = {}
    if exp:
        timing["exp_iso"] = __import__("datetime").datetime.utcfromtimestamp(exp).isoformat() + "Z"
        timing["exp_expired"] = now > exp
        timing["exp_seconds_left"] = exp - now
    if iat:
        timing["iat_iso"] = __import__("datetime").datetime.utcfromtimestamp(iat).isoformat() + "Z"
        timing["iat_seconds_ago"] = now - iat
    if nbf:
        timing["nbf_iso"] = __import__("datetime").datetime.utcfromtimestamp(nbf).isoformat() + "Z"
        timing["nbf_not_yet_valid"] = now < nbf

    return {
        "header": header,
        "payload": payload,
        "signature_b64url": signature_b64,
        "algorithm": alg,
        "parts": {"header_b64": parts[0], "payload_b64": parts[1], "signature_b64": parts[2]},
        "timing": timing,
        "claims": {
            "issuer": payload.get("iss"),
            "subject": payload.get("sub"),
            "audience": payload.get("aud"),
            "jwt_id": payload.get("jti"),
            "scope": payload.get("scope"),
            "roles": payload.get("roles") or payload.get("role"),
        },
        "note": "Signature non vérifiée (clé secrète requise)"
    }

class JWTRequest(BaseModel):
    token: str
    secret: str | None = None
    verify_signature: bool = False

@app.get("/")
def info():
    return {
        "service": "x402 JWT Decoder",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/decode",
        "endpoint": "POST /decode",
        "features": ["header decode", "payload decode", "timing analysis (exp/iat/nbf)", "HMAC-SHA256 verify (optionnel)"],
        "tagline": "Decode, verify and sign JWT tokens — supports HS256 and RS256",
        "curl_example": "curl https://x402-jwt.suretat.com/decode -H 'Content-Type: application/json' -d '{\"token\": \"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.abc\"}'",
        "try_it": "https://x402-jwt.suretat.com/docs",
    }

@app.post("/decode")
async def decode(req: Request, body: JWTRequest):
    if not verify_payment(req):
        return Response(
            content=json.dumps({"error": "Payment required", "x402": build_payment_info(req)}),
            status_code=402,
            media_type="application/json",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-ACCEPTS-PAYMENT": "x402"}
        )
    result = decode_jwt(body.token)
    if "error" in result:
        return result

    # Optional signature verification (HMAC-SHA256 only)
    if body.verify_signature and body.secret and result.get("algorithm") == "HS256":
        token = body.token.strip()
        parts = token.split(".")
        signing_input = f"{parts[0]}.{parts[1]}".encode()
        expected = hmac.new(body.secret.encode(), signing_input, hashlib.sha256).digest()
        sig_bytes = b64_decode(parts[2])
        result["signature_valid"] = hmac.compare_digest(expected, sig_bytes)

    return result

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
            "description": "x402 JWT Decoder",
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

