from __future__ import annotations
import io
import logging
import os
import time
from collections import Counter
from typing import Literal

import httpx
from PIL import Image
import uvicorn
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-colorpalette")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; x402-colorpalette/1.0)"}

app = FastAPI(title="x402 Color Palette Extractor", version="1.0.0")


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def rgb_to_hsl(r: int, g: int, b: int) -> tuple[int, int, int]:
    r_, g_, b_ = r / 255, g / 255, b / 255
    cmax, cmin = max(r_, g_, b_), min(r_, g_, b_)
    delta = cmax - cmin
    l = (cmax + cmin) / 2
    s = 0.0 if delta == 0 else delta / (1 - abs(2 * l - 1))
    if delta == 0:
        h = 0.0
    elif cmax == r_:
        h = 60 * (((g_ - b_) / delta) % 6)
    elif cmax == g_:
        h = 60 * ((b_ - r_) / delta + 2)
    else:
        h = 60 * ((r_ - g_) / delta + 4)
    return int(h), int(s * 100), int(l * 100)


def color_name(r: int, g: int, b: int) -> str:
    h, s, l = rgb_to_hsl(r, g, b)
    if l < 10: return "Noir"
    if l > 90: return "Blanc"
    if s < 15: return "Gris"
    if h < 15 or h >= 345: return "Rouge"
    if h < 45: return "Orange"
    if h < 75: return "Jaune"
    if h < 150: return "Vert"
    if h < 195: return "Cyan"
    if h < 255: return "Bleu"
    if h < 300: return "Violet"
    if h < 345: return "Rose"
    return "Inconnu"


def extract_palette(img: Image.Image, n_colors: int = 8) -> list[dict]:
    img = img.convert("RGBA").convert("RGB")
    img.thumbnail((200, 200))
    data = list(img.getdata())
    # Quantize using PIL
    qimg = img.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT)
    palette_data = qimg.getpalette()
    used_colors = set(qimg.getdata())
    result = []
    for idx in sorted(used_colors)[:n_colors]:
        r = palette_data[idx * 3]
        g = palette_data[idx * 3 + 1]
        b = palette_data[idx * 3 + 2]
        # Count pixels with this color
        count = sum(1 for px in qimg.getdata() if px == idx)
        percent = round(count / len(data) * 100, 1)
        h, s, l = rgb_to_hsl(r, g, b)
        result.append({
            "hex": rgb_to_hex(r, g, b),
            "rgb": {"r": r, "g": g, "b": b},
            "hsl": {"h": h, "s": s, "l": l},
            "nom": color_name(r, g, b),
            "pourcentage": percent,
        })
    result.sort(key=lambda x: -x["pourcentage"])
    return result


class URLRequest(BaseModel):
    url: str = Field(..., description="URL de l'image à analyser")
    n_colors: int = Field(default=8, ge=2, le=16, description="Nombre de couleurs dans la palette")


def _x402_response(url: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "x402Version": 1,
            "error": "Payment required",
            "accepts": [{
                "scheme": "exact",
                "network": NETWORK,
                "maxAmountRequired": PRICE_ATOMIC,
                "resource": url,
                "description": "Color palette extraction — 0.001 USDC",
                "mimeType": "application/json",
                "payTo": PAY_TO,
                "maxTimeoutSeconds": 300,
                "asset": ASSET_ADDRESS,
                "extra": {"name": "USDC", "version": "2"},
            }],
        },
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.get("/")
def root():
    return {
        "service": "x402 Color Palette Extractor",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.001 USDC/image",
        "endpoints": {
            "POST /from-url": "Extraire palette depuis URL",
            "POST /upload": "Extraire palette depuis fichier uploadé",
        },
        "docs": "/docs",
        "tagline": "Generate harmonious color palettes from a single seed color",
        "curl_example": "curl https://x402-colorpalette.suretat.com/palette -H 'Content-Type: application/json' -d '{\"color\": \"#3498db\", \"count\": 5, \"mode\": \"complementary\"}'",
        "try_it": "https://x402-colorpalette.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path in ("/from-url", "/upload") and request.method == "POST":
        auth = request.headers.get("X-PAYMENT") or request.headers.get("x-payment")
        if not auth:
            return _x402_response(str(request.url))
    return await call_next(request)


@app.post("/from-url")
async def from_url(req: URLRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(req.url)
        content_type = resp.headers.get("content-type", "")
        if not any(t in content_type for t in ("image/", "application/octet-stream")):
            return JSONResponse(status_code=400, content={"error": f"Pas une image: {content_type}"})
        img = Image.open(io.BytesIO(resp.content))
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e), "url": req.url})

    w, h = img.size
    palette = extract_palette(img, req.n_colors)
    return {
        "url": req.url,
        "dimensions": {"largeur": w, "hauteur": h},
        "n_couleurs": len(palette),
        "palette": palette,
    }


@app.post("/upload")
async def from_upload(request: Request, n_colors: int = 8):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        body = await request.body()
        img = Image.open(io.BytesIO(body))
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Image invalide: {e}"})

    w, h = img.size
    palette = extract_palette(img, min(max(2, n_colors), 16))
    return {
        "dimensions": {"largeur": w, "hauteur": h},
        "n_couleurs": len(palette),
        "palette": palette,
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
            "description": "x402 Color Palette Extractor",
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
    uvicorn.run(app, host="0.0.0.0", port=3060)
