from __future__ import annotations
import io
import base64
import logging
import os
import time
from typing import Literal

import barcode
from barcode.writer import ImageWriter, SVGWriter
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-barcode")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

BARCODE_TYPES = ["EAN13", "EAN8", "EAN14", "UPC-A", "ISBN13", "ISBN10", "ISSN", "Code39", "Code128", "PZN"]

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Barcode Generator", version="1.0.0")


class BarcodeRequest(BaseModel):
    data: str = Field(..., description="Données à encoder dans le code-barres")
    barcode_type: str = Field(default="EAN13", description=f"Type: {', '.join(BARCODE_TYPES)}")
    format: Literal["png", "svg", "base64"] = Field(default="png", description="Format de sortie")
    add_checksum: bool = Field(default=True, description="Ajouter le chiffre de contrôle (EAN/UPC)")
    text: str | None = Field(default=None, description="Texte affiché sous le code-barres (None = auto)")
    width: float = Field(default=10.0, ge=1.0, le=50.0, description="Largeur module (mm)")
    height: float = Field(default=15.0, ge=5.0, le=100.0, description="Hauteur barres (mm)")


@app.get("/")
def root():
    return {
        "service": "x402 Barcode Generator",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/code-barres",
        "endpoint": "POST /generate",
        "types": BARCODE_TYPES,
        "formats": ["png", "svg", "base64"],
        "docs": "/docs",
        "tagline": "Generate EAN13, Code128, QR barcodes as PNG",
        "curl_example": "curl https://x402-barcode.suretat.com/barcode -H 'Content-Type: application/json' -d '{\"data\": \"1234567890128\", \"type\": \"ean13\"}'",
        "try_it": "https://x402-barcode.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/generate" and request.method == "POST":
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
                        "description": "Barcode generation — 0.0005 USDC",
                        "mimeType": "image/png",
                        "payTo": PAY_TO,
                        "maxTimeoutSeconds": 300,
                        "asset": ASSET_ADDRESS,
                        "extra": {"name": "USDC", "version": "2"},
                    }],
                },
                headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
            )
    return await call_next(request)


@app.post("/generate")
def generate_barcode(req: BarcodeRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    bc_type = req.barcode_type.upper().replace("-", "")
    type_map = {"UPCA": "UPC-A", "EAN13": "EAN13", "EAN8": "EAN8", "CODE128": "Code128",
                "CODE39": "Code39", "ISBN13": "ISBN13", "ISBN10": "ISBN10",
                "ISSN": "ISSN", "EAN14": "EAN14", "PZN": "PZN"}
    actual_type = type_map.get(bc_type, req.barcode_type)

    try:
        bc_class = barcode.get_barcode_class(actual_type)
    except barcode.errors.BarcodeNotFoundError:
        return JSONResponse(status_code=400, content={
            "error": f"Type inconnu: {req.barcode_type}. Disponibles: {BARCODE_TYPES}"
        })

    options = {
        "module_width": req.width,
        "module_height": req.height,
        "write_text": True,
    }
    if req.text is not None:
        options["text"] = req.text

    try:
        if req.format == "svg":
            writer = SVGWriter()
            bc = bc_class(req.data, writer=writer)
            buf = io.BytesIO()
            bc.write(buf, options=options)
            return Response(content=buf.getvalue(), media_type="image/svg+xml")

        writer = ImageWriter()
        bc = bc_class(req.data, writer=writer)
        buf = io.BytesIO()
        bc.write(buf, options=options)
        png_bytes = buf.getvalue()

        if req.format == "base64":
            return {
                "image_base64": base64.b64encode(png_bytes).decode(),
                "size_bytes": len(png_bytes),
                "barcode_type": actual_type,
                "data": req.data,
            }

        return Response(content=png_bytes, media_type="image/png")

    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e), "data": req.data})



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
            "description": "x402 Barcode Generator",
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
    uvicorn.run(app, host="0.0.0.0", port=3050)
