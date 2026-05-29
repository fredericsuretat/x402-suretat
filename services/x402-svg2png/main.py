from __future__ import annotations
import os, time, base64, io
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import cairosvg

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 SVG2PNG", version="1.0.0")


def _make_402(host: str, endpoint: str = "/convert") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "SVG to PNG conversion with scale control",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/convert" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-svg2png.suretat.com"))
    return await call_next(request)


class ConvertRequest(BaseModel):
    svg: str  # SVG string or base64-encoded SVG
    width: Optional[int] = None
    height: Optional[int] = None
    scale: Optional[float] = 1.0
    background_color: Optional[str] = None  # e.g. "white" or "#FFFFFF"


@app.get("/")
def root():
    return {"service": "x402 SVG2PNG", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/convert")
def convert(req: ConvertRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    svg_data = req.svg.strip()

    # Detect if base64
    if not svg_data.startswith("<"):
        try:
            svg_bytes = base64.b64decode(svg_data)
        except Exception:
            return JSONResponse(status_code=422, content={"error": "Input must be SVG string or base64-encoded SVG"})
    else:
        svg_bytes = svg_data.encode("utf-8")

    if len(svg_bytes) > 5 * 1024 * 1024:  # 5MB limit
        return JSONResponse(status_code=413, content={"error": "SVG too large (max 5MB)"})

    scale = req.scale or 1.0
    if scale <= 0 or scale > 10:
        return JSONResponse(status_code=400, content={"error": "scale must be between 0 and 10"})

    try:
        png_bytes = cairosvg.svg2png(
            bytestring=svg_bytes,
            output_width=req.width,
            output_height=req.height,
            scale=scale,
            background_color=req.background_color,
        )
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Conversion failed: {str(e)}"})

    # Get dimensions from PNG header
    width = height = None
    if png_bytes and len(png_bytes) > 24:
        import struct
        width = struct.unpack(">I", png_bytes[16:20])[0]
        height = struct.unpack(">I", png_bytes[20:24])[0]

    return {
        "png_base64": base64.b64encode(png_bytes).decode("utf-8"),
        "width": width,
        "height": height,
        "size_bytes": len(png_bytes),
        "scale": scale,
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-svg2png.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/convert",
        "description": "SVG to PNG conversion with scale control",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3106, proxy_headers=True, forwarded_allow_ips="*")
