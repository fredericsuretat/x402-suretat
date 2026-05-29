from __future__ import annotations
import os, time, base64, io
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import httpx
from PIL import Image, ImageStat
from collections import Counter

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Image Info", version="1.0.0")


def _make_402(host: str, endpoint: str = "/analyze") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "Image analysis: format, dimensions, colors, transparency",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/analyze" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-image-info.suretat.com"))
    return await call_next(request)


class AnalyzeRequest(BaseModel):
    url: Optional[str] = None
    image_base64: Optional[str] = None
    top_colors: Optional[int] = 5


def get_dominant_colors(img: Image.Image, n: int = 5) -> List[str]:
    """Get top N dominant colors as hex strings using quantization."""
    # Resize for performance
    small = img.copy()
    small.thumbnail((100, 100), Image.LANCZOS)

    # Convert to RGB
    if small.mode not in ("RGB", "RGBA"):
        small = small.convert("RGB")
    elif small.mode == "RGBA":
        bg = Image.new("RGB", small.size, (255, 255, 255))
        bg.paste(small, mask=small.split()[3])
        small = bg

    # Quantize to reduce colors
    try:
        quantized = small.quantize(colors=n * 4)
        palette = quantized.getpalette()
        counts_by_color = {}
        pixels = list(quantized.getdata())
        count = Counter(pixels)
        top_indices = [idx for idx, _ in count.most_common(n)]
        colors = []
        for i in top_indices[:n]:
            r = palette[i * 3]
            g = palette[i * 3 + 1]
            b = palette[i * 3 + 2]
            colors.append(f"#{r:02X}{g:02X}{b:02X}")
        return colors
    except Exception:
        # Fallback: sample pixels
        pixels_rgb = list(small.getdata())
        bucket_size = 32
        buckets: Counter = Counter()
        for px in pixels_rgb:
            if isinstance(px, (list, tuple)) and len(px) >= 3:
                r = (px[0] // bucket_size) * bucket_size
                g = (px[1] // bucket_size) * bucket_size
                b = (px[2] // bucket_size) * bucket_size
                buckets[(r, g, b)] += 1
        top = [f"#{r:02X}{g:02X}{b:02X}" for (r, g, b), _ in buckets.most_common(n)]
        return top


def analyze_image(img_bytes: bytes, file_size: int) -> dict:
    buf = io.BytesIO(img_bytes)
    try:
        img = Image.open(buf)
        img.load()
    except Exception as e:
        return {"error": f"Failed to open image: {str(e)}"}

    fmt = img.format or "unknown"
    width, height = img.size
    mode = img.mode
    has_transparency = mode in ("RGBA", "LA", "P") or (mode == "P" and "transparency" in img.info)
    is_animated = getattr(img, "is_animated", False) or (hasattr(img, "n_frames") and img.n_frames > 1)
    n_frames = getattr(img, "n_frames", 1)

    # Dominant colors
    top_n = 5
    try:
        dominant_colors = get_dominant_colors(img, top_n)
    except Exception:
        dominant_colors = []

    # Stats
    try:
        if mode not in ("RGB", "L"):
            img_rgb = img.convert("RGB")
        else:
            img_rgb = img
        stat = ImageStat.Stat(img_rgb)
        mean_rgb = [round(v, 1) for v in stat.mean[:3]]
    except Exception:
        mean_rgb = None

    return {
        "format": fmt,
        "width": width,
        "height": height,
        "aspect_ratio": round(width / height, 4) if height > 0 else None,
        "color_mode": mode,
        "has_transparency": has_transparency,
        "is_animated": is_animated,
        "n_frames": n_frames,
        "file_size_bytes": file_size,
        "file_size_kb": round(file_size / 1024, 2),
        "dominant_colors": dominant_colors,
        "mean_rgb": mean_rgb,
    }


@app.get("/")
def root():
    return {"service": "x402 Image Info", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if not req.url and not req.image_base64:
        return JSONResponse(status_code=400, content={"error": "Provide either url or image_base64"})

    img_bytes = None
    source = None

    if req.url:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(req.url)
                response.raise_for_status()
                img_bytes = response.content
                source = str(response.url)
        except httpx.HTTPStatusError as e:
            return JSONResponse(status_code=502, content={"error": f"HTTP {e.response.status_code} from URL"})
        except httpx.RequestError as e:
            return JSONResponse(status_code=502, content={"error": f"Failed to fetch URL: {str(e)}"})
    else:
        try:
            img_bytes = base64.b64decode(req.image_base64)
            source = "base64"
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": f"Invalid base64: {str(e)}"})

    if len(img_bytes) > 20 * 1024 * 1024:
        return JSONResponse(status_code=413, content={"error": "Image too large (max 20MB)"})

    result = analyze_image(img_bytes, len(img_bytes))

    if "error" in result:
        return JSONResponse(status_code=422, content=result)

    return {"source": source, **result}


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-image-info.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/analyze",
        "description": "Image analysis: format, dimensions, colors, transparency",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3113, proxy_headers=True, forwarded_allow_ips="*")
