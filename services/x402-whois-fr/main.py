"""
x402 Whois FR — Whois enrichi pour domaines .fr et génériques
- Propriétaire (RGPD: masqué si particulier)
- Dates création/expiration/mise à jour
- Nameservers / bureaux registraires
- Statut domaine (active, redemptionPeriod, etc.)
Prix: 0.001 USDC/appel
"""
from __future__ import annotations
import os, re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import whois
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

WALLET       = os.getenv("WALLET_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
FACILITATOR  = os.getenv("FACILITATOR_URL", "https://api.cdp.coinbase.com/platform/v2/x402")
USDC_BASE    = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

payments_total = 0
payments_log: list = []

DOMAIN_RE = re.compile(
    r'^(?:[a-zA-Z0-9]'
    r'(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)'
    r'+[a-zA-Z]{2,}$'
)

PAYMENT_REQUIREMENTS = {
    "scheme": "exact",
    "network": "base",
    "maxAmountRequired": PRICE_ATOMIC,
    "resource": "https://x402-whois.suretat.com/whois",
    "description": "Whois enrichi domaines .fr et génériques — RGPD, dates, nameservers",
    "mimeType": "application/json",
    "payTo": WALLET,
    "maxTimeoutSeconds": 300,
    "asset": USDC_BASE,
    "extra": {
        "name": "USD Coin",
        "version": "2",
        "bazaar": {
            "bodyType": "json",
            "input": {"domain": "exemple.fr"},
            "inputSchema": {
                "properties": {
                    "domain": {"type": "string", "description": "Domaine à analyser (ex: google.fr)"}
                },
                "required": ["domain"],
            },
            "output": {
                "example": {
                    "domain": "exemple.fr",
                    "registrar": "OVH",
                    "creation_date": "2002-01-01",
                    "expiration_date": "2026-01-01",
                    "status": ["active"],
                    "name_servers": ["ns1.ovh.net", "ns2.ovh.net"],
                    "rgpd_masked": True,
                }
            },
        },
    },
}


def _fmt_date(d) -> str | None:
    if not d:
        return None
    if isinstance(d, list):
        d = d[0]
    try:
        return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
    except Exception:
        return str(d)[:10]


def do_whois(domain: str) -> dict:
    domain = domain.strip().lower()
    if not DOMAIN_RE.match(domain):
        return {"error": f"Domaine invalide: '{domain}'"}
    try:
        w = whois.whois(domain)
    except whois.parser.PywhoisError as e:
        return {"error": f"Whois error: {str(e)[:200]}"}
    except Exception as e:
        return {"error": f"Erreur: {str(e)[:200]}"}

    if not w or not w.domain_name:
        return {"error": "Domaine non trouvé ou whois non disponible"}

    status = w.status
    if isinstance(status, str):
        status = [status]
    name_servers = w.name_servers
    if isinstance(name_servers, str):
        name_servers = [name_servers]
    if name_servers:
        name_servers = sorted(set(s.lower().rstrip(".") for s in name_servers if s))

    registrant = w.get("registrant") or w.get("org") or w.get("organization")
    rgpd_masked = bool(
        not registrant
        or "REDACTED" in str(registrant).upper()
        or "PRIVACY" in str(registrant).upper()
        or "GDPR" in str(registrant).upper()
        or "RGPD" in str(registrant).upper()
    )

    result = {
        "domain": domain,
        "domain_name": w.domain_name if isinstance(w.domain_name, str) else (w.domain_name[0] if w.domain_name else None),
        "registrar": w.registrar,
        "registrant": None if rgpd_masked else registrant,
        "rgpd_masked": rgpd_masked,
        "creation_date": _fmt_date(w.creation_date),
        "expiration_date": _fmt_date(w.expiration_date),
        "updated_date": _fmt_date(w.updated_date),
        "status": status or [],
        "name_servers": (name_servers or [])[:10],
        "dnssec": getattr(w, "dnssec", None),
        "emails": (w.emails if isinstance(w.emails, list) else ([w.emails] if w.emails else [])),
    }
    # Calcul du nombre de jours avant expiration
    if result["expiration_date"]:
        try:
            exp = datetime.strptime(result["expiration_date"], "%Y-%m-%d")
            result["days_until_expiry"] = (exp - datetime.now()).days
        except Exception:
            pass
    return result


async def cdp_call(endpoint: str, payment_header: str) -> bool:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{FACILITATOR}/{endpoint}",
                json={
                    "x402Version": 1,
                    "paymentHeader": payment_header,
                    "paymentRequirements": [PAYMENT_REQUIREMENTS],
                },
            )
            if endpoint == "verify":
                return resp.json().get("isValid", False)
            return resp.status_code == 200
        except Exception:
            return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[x402-whois] Wallet: {WALLET}")
    yield


app = FastAPI(title="x402 Whois FR", version="1.0.0", lifespan=lifespan)


class WhoisRequest(BaseModel):
    domain: str


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if not request.url.path.startswith("/whois"):
        return await call_next(request)
    payment_header = request.headers.get("X-PAYMENT")
    if not payment_header:
        return JSONResponse(
            status_code=402,
            content={"x402Version": 1, "accepts": [PAYMENT_REQUIREMENTS], "error": "Payment required"},
                    headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
        )
    if not await cdp_call("verify", payment_header):
        return JSONResponse(
            status_code=402,
            content={"x402Version": 1, "error": "Paiement invalide ou expiré"},
                    headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
        )
    response = await call_next(request)
    await cdp_call("settle", payment_header)
    global payments_total, payments_log
    payments_total += 1
    payments_log.append({"n": payments_total, "at": datetime.now(timezone.utc).isoformat()})
    if len(payments_log) > 100:
        payments_log = payments_log[-100:]
    print(f"[x402-whois] PAIEMENT #{payments_total}")
    return response


@app.get("/")
async def root():
    return {
        "service": "x402 Whois FR",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.001 USDC/appel",
        "endpoint": "POST /whois",
        "body": {"domain": "exemple.fr"},
        "features": ["registrar", "dates création/expiration", "nameservers", "statut RGPD", "jours restants"],
        "docs": "/docs",
        "tagline": "WHOIS lookup for .fr and generic domains — registrar, creation date, status",
        "curl_example": "curl https://x402-whois-fr.suretat.com/whois -H 'Content-Type: application/json' -d '{\"domain\": \"lemonde.fr\"}'",
        "try_it": "https://x402-whois-fr.suretat.com/docs",
    }


@app.post("/whois")
async def whois_lookup(payload: WhoisRequest):
    if not payload.domain or not payload.domain.strip():
        return JSONResponse(status_code=400, content={"error": "Champ 'domain' requis"})
    result = do_whois(payload.domain)
    if "error" in result:
        return JSONResponse(status_code=400 if "invalide" in result["error"] else 502, content=result)
    return result


@app.get("/stats")
async def stats():
    return {"service": "x402-whois-fr", "payments_total": payments_total, "last_payments": payments_log[-10:]}

@app.get("/.well-known/x402.json")
async def x402_well_known():
    return {"x402Version": 1, "accepts": [PAYMENT_REQUIREMENTS]}

@app.get("/.well-known/x402")
async def x402_well_known_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/.well-known/x402.json")

