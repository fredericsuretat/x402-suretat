from __future__ import annotations
import io
import base64
import logging
import os
import time
from typing import Literal

import qrcode
from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H
from qrcode.image.styledpil import StyledPilImage
from PIL import Image
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-qrcode")

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO       = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK      = os.getenv("NETWORK", "base")
FACILITATOR  = os.getenv("FACILITATOR", "https://api.cdp.coinbase.com/platform/v2/x402")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 QR Code Generator", version="1.0.0")

EC_MAP = {
    "L": ERROR_CORRECT_L,
    "M": ERROR_CORRECT_M,
    "Q": ERROR_CORRECT_Q,
    "H": ERROR_CORRECT_H,
}

class QRRequest(BaseModel):
    text: str = Field(..., description="Texte ou URL à encoder", max_length=2000)
    size: int = Field(default=10, ge=1, le=40, description="Taille des modules (1-40)")
    border: int = Field(default=4, ge=0, le=20, description="Marge en modules")
    error_correction: Literal["L", "M", "Q", "H"] = Field(default="M", description="Niveau de correction d'erreur")
    fill_color: str = Field(default="#000000", description="Couleur du QR code (hex)")
    back_color: str = Field(default="#FFFFFF", description="Couleur de fond (hex)")
    format: Literal["png", "svg", "base64"] = Field(default="png", description="Format de sortie")
    scale: int = Field(default=1, ge=1, le=4, description="Facteur de zoom (1-4)")


@app.get("/")
def root():
    return {
        "service": "x402 QR Code Generator",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"0.0005 USDC/QR",
        "endpoint": "POST /generate",
        "formats": ["png", "svg", "base64"],
        "docs": "/docs",
        "tagline": "Generate QR codes as PNG or SVG from any text or URL",
        "curl_example": "curl https://x402-qrcode.suretat.com/qrcode -H 'Content-Type: application/json' -d '{\"data\": \"https://example.com\", \"format\": \"png\"}'",
        "try_it": "https://x402-qrcode.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    uptime = int(time.time() - stats["start_time"])
    return {**stats, "uptime_seconds": uptime}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/generate" and request.method == "POST":
        auth = request.headers.get("X-PAYMENT") or request.headers.get("x-payment")
        if not auth:
            log.info("402 returned — missing X-PAYMENT header")
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
                        "description": "QR Code generation — 0.0005 USDC",
                        "mimeType": "image/png",
                        "payTo": PAY_TO,
                        "maxTimeoutSeconds": 300,
                        "asset": ASSET_ADDRESS,
                        "extra": {"name": "USDC", "version": "2"},
                    }],
                },
                headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
            )
    response = await call_next(request)
    return response


@app.post("/generate")
async def generate_qr(req: QRRequest, request: Request):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    ec = EC_MAP.get(req.error_correction, ERROR_CORRECT_M)
    qr = qrcode.QRCode(
        version=None,
        error_correction=ec,
        box_size=req.size * req.scale,
        border=req.border,
    )
    qr.add_data(req.text)
    qr.make(fit=True)

    if req.format == "svg":
        import qrcode.image.svg as svg_mod
        factory = svg_mod.SvgImage
        img = qr.make_image(image_factory=factory, fill_color=req.fill_color, back_color=req.back_color)
        buf = io.BytesIO()
        img.save(buf)
        svg_bytes = buf.getvalue()
        return Response(content=svg_bytes, media_type="image/svg+xml")

    img = qr.make_image(fill_color=req.fill_color, back_color=req.back_color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    if req.format == "base64":
        return {
            "image_base64": base64.b64encode(png_bytes).decode(),
            "size_bytes": len(png_bytes),
            "format": "png",
            "text_length": len(req.text),
        }

    return Response(content=png_bytes, media_type="image/png")



@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK if "NETWORK" in dir() else os.getenv("NETWORK", "base"),
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/generate",
            "description": "x402 QR Code Generator",
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
    uvicorn.run(app, host="0.0.0.0", port=3042)
