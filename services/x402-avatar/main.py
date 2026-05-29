from __future__ import annotations
import os, time, base64, hashlib, io, math
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Avatar", version="1.0.0")

AVATAR_COLORS = [
    "#E74C3C", "#E67E22", "#F1C40F", "#2ECC71", "#1ABC9C",
    "#3498DB", "#9B59B6", "#E91E63", "#FF5722", "#009688",
    "#673AB7", "#2196F3", "#00BCD4", "#8BC34A", "#FF9800",
    "#795548", "#607D8B", "#F44336", "#4CAF50", "#03A9F4",
]


def _seed_hash(seed: str) -> int:
    return int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16)


def hex_to_rgb_tuple(hex_str: str) -> tuple:
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def generate_initials(seed: str, size: int, bg_color: str) -> bytes:
    h = _seed_hash(seed)
    color = AVATAR_COLORS[h % len(AVATAR_COLORS)]

    # Extract initials: up to 2 chars from words or email
    text = seed.split("@")[0].replace(".", " ").replace("_", " ").replace("-", " ")
    words = [w for w in text.split() if w]
    if len(words) >= 2:
        initials = (words[0][0] + words[1][0]).upper()
    elif words:
        initials = words[0][:2].upper()
    else:
        initials = seed[:2].upper()

    img = Image.new("RGB", (size, size), color=hex_to_rgb_tuple(bg_color) if bg_color else hex_to_rgb_tuple(color))
    draw = ImageDraw.Draw(img)

    # Draw background color circle
    bg_rgb = hex_to_rgb_tuple(bg_color) if bg_color else (255, 255, 255)
    fg_rgb = hex_to_rgb_tuple(color)
    img = Image.new("RGB", (size, size), fg_rgb)
    draw = ImageDraw.Draw(img)

    # Text
    font_size = size // 2
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except (IOError, OSError):
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), initials, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) // 2
    y = (size - th) // 2
    draw.text((x, y), initials, fill="white", font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_identicon(seed: str, size: int, bg_color: str) -> bytes:
    h = _seed_hash(seed)
    color = AVATAR_COLORS[h % len(AVATAR_COLORS)]
    fg_rgb = hex_to_rgb_tuple(color)
    bg_rgb = hex_to_rgb_tuple(bg_color) if bg_color else (240, 240, 240)

    cell_size = size // 5
    actual_size = cell_size * 5

    img = Image.new("RGB", (actual_size, actual_size), bg_rgb)
    draw = ImageDraw.Draw(img)

    bits = (h >> 8) & 0xFFFFFFFF
    for row in range(5):
        for col in range(3):  # Only 3 columns, mirrored
            if bits & 1:
                x = col * cell_size
                y = row * cell_size
                draw.rectangle([x, y, x + cell_size - 1, y + cell_size - 1], fill=fg_rgb)
                # Mirror
                mirror_col = 4 - col
                if mirror_col != col:
                    x2 = mirror_col * cell_size
                    draw.rectangle([x2, y, x2 + cell_size - 1, y + cell_size - 1], fill=fg_rgb)
            bits >>= 1

    if actual_size != size:
        img = img.resize((size, size), Image.NEAREST)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_pixel(seed: str, size: int, bg_color: str) -> bytes:
    h = _seed_hash(seed)
    bg_rgb = hex_to_rgb_tuple(bg_color) if bg_color else (20, 20, 30)

    pixel_count = 8
    cell_size = size // pixel_count
    actual_size = cell_size * pixel_count

    img = Image.new("RGB", (actual_size, actual_size), bg_rgb)
    draw = ImageDraw.Draw(img)

    rng = h
    for row in range(pixel_count):
        for col in range(pixel_count):
            rng = (rng * 1664525 + 1013904223) & 0xFFFFFFFF
            if rng % 3 != 0:
                r = (rng >> 16) & 0xFF
                g = (rng >> 8) & 0xFF
                b = rng & 0xFF
                x = col * cell_size
                y = row * cell_size
                draw.rectangle([x, y, x + cell_size - 1, y + cell_size - 1], fill=(r, g, b))

    if actual_size != size:
        img = img.resize((size, size), Image.NEAREST)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_402(host: str, endpoint: str = "/generate") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "Deterministic avatar generation (identicon/initials/pixel)",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/generate" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-avatar.suretat.com"))
    return await call_next(request)


class GenerateRequest(BaseModel):
    seed: str
    style: Optional[str] = "identicon"  # identicon, initials, pixel
    size: Optional[int] = 128
    bg_color: Optional[str] = None


@app.get("/")
def root():
    return {"service": "x402 Avatar", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/generate")
def generate(req: GenerateRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    size = max(16, min(512, req.size or 128))
    style = (req.style or "identicon").lower()

    if style == "initials":
        png_bytes = generate_initials(req.seed, size, req.bg_color or "")
    elif style == "pixel":
        png_bytes = generate_pixel(req.seed, size, req.bg_color or "")
    else:
        png_bytes = generate_identicon(req.seed, size, req.bg_color or "")

    return {
        "png_base64": base64.b64encode(png_bytes).decode("utf-8"),
        "seed": req.seed,
        "style": style,
        "size": size,
        "size_bytes": len(png_bytes),
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-avatar.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/generate",
        "description": "Deterministic avatar generation (identicon/initials/pixel)",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3107, proxy_headers=True, forwarded_allow_ips="*")
