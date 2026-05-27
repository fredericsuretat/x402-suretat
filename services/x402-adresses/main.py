import os
import base64
import json
import time
import secrets
import httpx
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

PRICE_USDC = os.getenv("PRICE_USDC", "0.001")
FACILITATOR_URL = os.getenv("FACILITATOR_URL", "https://x402.org/facilitator")
CDP_API_KEY_ID     = os.getenv("CDP_API_KEY_ID")
CDP_API_KEY_SECRET = os.getenv("CDP_API_KEY_SECRET")

def _cdp_jwt(method: str, path: str) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    raw = base64.b64decode(CDP_API_KEY_SECRET)
    private_key = Ed25519PrivateKey.from_private_bytes(raw[:32])
    now = int(time.time())
    nonce = secrets.token_hex(16)
    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
    header = b64url(json.dumps({"alg": "EdDSA", "typ": "JWT", "kid": CDP_API_KEY_ID, "nonce": nonce}).encode())
    payload = b64url(json.dumps({"sub": CDP_API_KEY_ID, "iss": "cdp", "nbf": now, "exp": now + 120, "uri": f"{method} api.cdp.coinbase.com{path}"}).encode())
    sig = b64url(private_key.sign(f"{header}.{payload}".encode()))
    return f"{header}.{payload}.{sig}"
BAN_API = "https://api-adresse.data.gouv.fr/search/"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

wallet_address: str = ""
payments_total: int = 0
payments_log: list = []


async def resolve_wallet() -> str:
    raw = os.getenv("WALLET_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
    if raw.startswith("0x"):
        return raw
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"https://api.ensdata.net/{raw}")
            resolved = resp.json().get("address")
            if resolved:
                print(f"[x402] {raw} → {resolved}")
                return resolved
        except Exception:
            pass
    print(f"[x402] Impossible de résoudre {raw}, utilisation brute")
    return raw


@asynccontextmanager
async def lifespan(app: FastAPI):
    global wallet_address
    wallet_address = await resolve_wallet()
    if not wallet_address:
        print("[x402] AVERTISSEMENT : WALLET_ADDRESS non défini, les paiements ne seront pas encaissés")
    else:
        print(f"[x402] Wallet actif : {wallet_address}")
    yield


app = FastAPI(title="Validateur Adresses FR", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-PAYMENT", "Authorization"],
    expose_headers=["X-PAYMENT-RESPONSE"],
)


class AddressRequest(BaseModel):
    adresse: str


BAZAAR_EXTENSION = {
    "name": "USDC",
    "version": "2",
    "bazaar": {
        "discoverable": True,
        "category": "data",
        "tags": ["adresse", "france", "geocoding", "validation", "ban", "postal"],
        "bodyType": "json",
        "input": {"adresse": "15 rue de la paix paris"},
        "inputSchema": {
            "type": "object",
            "properties": {
                "adresse": {"type": "string", "description": "Adresse française à valider et normaliser"}
            },
            "required": ["adresse"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "valide": {"type": "boolean"},
                "adresse_normalisee": {"type": "string"},
                "score": {"type": "number"},
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "ville": {"type": "string"},
                "code_postal": {"type": "string"},
            },
        },
    },
}


def build_payment_requirements(resource_url: str) -> dict:
    if resource_url.startswith("http://"):
        resource_url = "https://" + resource_url[7:]
    return {
        "scheme": "exact",
        "network": "base",
        "maxAmountRequired": PRICE_USDC,
        "resource": resource_url,
        "description": "Validation d'adresse française — Base Adresse Nationale",
        "mimeType": "application/json",
        "payTo": wallet_address,
        "maxTimeoutSeconds": 300,
        "asset": USDC_BASE,
        "extra": BAZAAR_EXTENSION,
    }


async def call_facilitator(endpoint: str, payment_header: str, requirements: dict) -> bool:
    use_cdp = bool(CDP_API_KEY_ID and CDP_API_KEY_SECRET)
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            headers = {"Content-Type": "application/json"}
            if use_cdp:
                payment = json.loads(base64.b64decode(payment_header).decode())
                body = {"x402Version": 1, "paymentPayload": payment, "paymentRequirements": [requirements]}
                headers["Authorization"] = f"Bearer {_cdp_jwt('POST', f'/platform/v2/x402/{endpoint}')}"
            else:
                body = {"x402Version": 1, "paymentHeader": payment_header, "paymentRequirements": [requirements]}
            resp = await client.post(
                f"{FACILITATOR_URL}/{endpoint}",
                json=body,
                headers=headers,
            )
            if endpoint == "verify":
                return resp.json().get("isValid", False)
            return resp.status_code == 200
        except Exception:
            return False


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if not request.url.path.startswith("/validate"):
        return await call_next(request)

    # Let OPTIONS (CORS preflight) pass through
    if request.method == "OPTIONS":
        return await call_next(request)

    requirements = build_payment_requirements(str(request.url))
    payment_header = request.headers.get("X-PAYMENT")

    if not payment_header:
        return JSONResponse(
            status_code=402,
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
            content={
                "x402Version": 1,
                "accepts": [requirements],
                "error": "Payment required",
            },
        )

    is_valid = await call_facilitator("verify", payment_header, requirements)
    if not is_valid:
        return JSONResponse(
            status_code=402,
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
            content={"x402Version": 1, "error": "Paiement invalide ou expiré"},
        )

    settled = await call_facilitator("settle", payment_header, requirements)
    if settled:
        global payments_total, payments_log
        payments_total += 1
        from datetime import datetime, timezone
        payments_log.append({
            "n": payments_total,
            "at": datetime.now(timezone.utc).isoformat(),
            "resource": "https://" + request.headers.get("host", str(request.url.hostname)) + str(request.url.path),
        })
        if len(payments_log) > 100:
            payments_log = payments_log[-100:]
        print(f"[x402] PAIEMENT #{payments_total} reçu — {request.url}")
    return await call_next(request)


@app.get("/.well-known/x402.json")
async def x402_discovery(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "x402Version": 1,
        "endpoints": [
            {"path": "/validate", "method": "POST", "price": PRICE_USDC, "network": "base",
             "asset": USDC_BASE, "payTo": wallet_address,
             "description": "Validation d'adresse française — Base Adresse Nationale"},
        ],
        "docs": f"{base}/docs",
        "health": f"{base}/health",
        "stats": f"{base}/stats",
    }


@app.get("/")
async def root():
    return {
        "service": "Validateur Adresses Françaises",
        "protocol": "x402",
        "network": "Base (Coinbase L2)",
        "price_per_call": f"{PRICE_USDC} USDC",
        "endpoint": "POST /validate",
        "body": {"adresse": "string"},
        "docs": "/docs",
        "tagline": "Validate and normalize French postal addresses via BAN API",
        "curl_example": "curl https://x402-adresses.suretat.com/validate -H 'Content-Type: application/json' -d '{\"adresse\": \"1 place du general de Gaulle, 59000 Lille\"}'",
        "try_it": "https://x402-adresses.suretat.com/docs",
    }


@app.post("/validate")
async def validate_address(payload: AddressRequest):
    adresse = payload.adresse.strip()
    if not adresse:
        return JSONResponse(status_code=400, content={"error": "Champ 'adresse' requis"})

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(BAN_API, params={"q": adresse, "limit": 1})
            data = resp.json()
        except Exception:
            return JSONResponse(status_code=503, content={"error": "Service BAN indisponible"})

    if not data.get("features"):
        return {"valide": False, "score": 0.0, "adresse_originale": adresse}

    feature = data["features"][0]
    props = feature["properties"]
    lon, lat = feature["geometry"]["coordinates"]

    return {
        "valide": True,
        "adresse_normalisee": props.get("label"),
        "numero": props.get("housenumber"),
        "rue": props.get("street") or props.get("name"),
        "code_postal": props.get("postcode"),
        "ville": props.get("city"),
        "departement": props.get("context", "").split(",")[0].strip() if props.get("context") else None,
        "score": round(props.get("score", 0), 4),
        "lat": lat,
        "lon": lon,
        "type": props.get("type"),
        "adresse_originale": adresse,
    }


@app.get("/stats")
async def stats():
    return {
        "payments_total": payments_total,
        "revenue_usdc": round(payments_total * float(PRICE_USDC), 8),
        "price_usdc": PRICE_USDC,
        "last_payments": payments_log[-5:] if payments_log else [],
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
