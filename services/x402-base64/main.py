import os
import json
import base64
import binascii
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
USDC_ADDRESS = os.getenv("USDC_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
NETWORK = os.getenv("NETWORK", "base")

app = FastAPI(title="x402 Base Encoder", version="1.0.0")

PAYMENT_INFO = {
    "x402Version": 1,
    "accepts": [{
        "scheme": "exact",
        "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"http://{os.getenv('HOST', 'localhost')}:{os.getenv('PORT', '3065')}/encode",
        "description": "Base Encoder/Decoder",
        "mimeType": "application/json",
        "payTo": PAY_TO,
        "maxTimeoutSeconds": 300,
        "asset": USDC_ADDRESS,
        "extra": {"name": "USD Coin", "version": "2"}
    }]
}

def verify_payment(request: Request) -> bool:
    return bool(request.headers.get("X-PAYMENT") or request.headers.get("x-payment", ""))

ENCODINGS = {
    "base16": {"encode": lambda b: base64.b16encode(b).decode(), "decode": lambda s: base64.b16decode(s.upper())},
    "hex": {"encode": lambda b: b.hex(), "decode": lambda s: bytes.fromhex(s.replace(" ", "").replace(":", ""))},
    "base32": {"encode": lambda b: base64.b32encode(b).decode(), "decode": lambda s: base64.b32decode(s + "=" * (-len(s) % 8))},
    "base32hex": {"encode": lambda b: base64.b32hexencode(b).decode(), "decode": lambda s: base64.b32hexdecode(s + "=" * (-len(s) % 8))},
    "base64": {"encode": lambda b: base64.b64encode(b).decode(), "decode": lambda s: base64.b64decode(s + "==")},
    "base64url": {"encode": lambda b: base64.urlsafe_b64encode(b).decode().rstrip("="), "decode": lambda s: base64.urlsafe_b64decode(s + "==")},
    "base85": {"encode": lambda b: base64.b85encode(b).decode(), "decode": lambda s: base64.b85decode(s)},
    "ascii85": {"encode": lambda b: base64.a85encode(b).decode(), "decode": lambda s: base64.a85decode(s)},
}

class EncodeRequest(BaseModel):
    texte: str | None = Field(default=None, description="Texte à encoder (UTF-8)")
    hex_input: str | None = Field(default=None, description="Données en hex à encoder")
    encodages: list[str] = Field(default=["base64", "base64url", "hex"], description="Encodages cibles")
    charset: str = Field(default="utf-8", description="Charset pour texte: utf-8, latin-1, ascii")

class DecodeRequest(BaseModel):
    valeur: str = Field(description="Chaîne à décoder")
    encodage: str = Field(description="Encodage source: base64, base64url, base32, hex, base16, base85, ascii85")
    output: str = Field(default="texte", description="Format de sortie: texte, hex, base64")
    charset: str = Field(default="utf-8", description="Charset pour décodage texte")

@app.get("/")
def info():
    return {
        "service": "x402 Base Encoder",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoints": ["POST /encode", "POST /decode"],
        "encodages": list(ENCODINGS.keys()),
        "docs": "/docs",
        "tagline": "Encode/decode Base64, Base32, Base58, URL-safe variants",
        "curl_example": "curl https://x402-base64.suretat.com/encode -H 'Content-Type: application/json' -d '{\"data\": \"Hello World\", \"encoding\": \"base64\"}'",
        "try_it": "https://x402-base64.suretat.com/docs",
    }

@app.post("/encode")
async def encode(req: Request, body: EncodeRequest):
    if not verify_payment(req):
        return Response(content=json.dumps({"error": "Payment required", "x402": PAYMENT_INFO}),
                        status_code=402, media_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-ACCEPTS-PAYMENT": "x402"})
    try:
        if body.texte is not None:
            raw = body.texte.encode(body.charset)
            source = "texte"
        elif body.hex_input is not None:
            raw = bytes.fromhex(body.hex_input.replace(" ", "").replace(":", ""))
            source = "hex"
        else:
            return {"error": "Fournir 'texte' ou 'hex_input'"}
    except (UnicodeEncodeError, ValueError) as e:
        return {"error": f"Encodage source invalide: {e}"}

    results = {}
    for enc in body.encodages:
        enc_lower = enc.lower()
        if enc_lower not in ENCODINGS:
            results[enc] = f"Encodage inconnu (disponibles: {', '.join(ENCODINGS)})"
            continue
        try:
            results[enc_lower] = ENCODINGS[enc_lower]["encode"](raw)
        except Exception as e:
            results[enc_lower] = f"Erreur: {e}"

    return {
        "source": source,
        "longueur_octets": len(raw),
        "resultats": results
    }

@app.post("/decode")
async def decode(req: Request, body: DecodeRequest):
    if not verify_payment(req):
        return Response(content=json.dumps({"error": "Payment required", "x402": PAYMENT_INFO}),
                        status_code=402, media_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-ACCEPTS-PAYMENT": "x402"})
    enc = body.encodage.lower()
    if enc not in ENCODINGS:
        return {"error": f"Encodage inconnu: {body.encodage}. Disponibles: {', '.join(ENCODINGS)}"}
    try:
        raw = ENCODINGS[enc]["decode"](body.valeur.strip())
    except Exception as e:
        return {"error": f"Décodage impossible ({enc}): {e}"}

    result = {"encodage": enc, "longueur_octets": len(raw)}
    out = body.output.lower()
    if out == "texte":
        try:
            result["texte"] = raw.decode(body.charset)
        except UnicodeDecodeError as e:
            result["texte"] = None
            result["warning"] = f"Non décodable en {body.charset}: {e}"
            result["hex"] = raw.hex()
    elif out == "hex":
        result["hex"] = raw.hex()
    elif out == "base64":
        result["base64"] = base64.b64encode(raw).decode()
    else:
        result["hex"] = raw.hex()

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
            "description": "x402 Base Encoder",
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

