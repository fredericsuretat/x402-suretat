from __future__ import annotations
import os, time, math
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import colorsys

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Color Convert", version="1.0.0")

# CSS named colors (subset)
CSS_COLORS = {
    "red": (255,0,0), "green": (0,128,0), "blue": (0,0,255), "white": (255,255,255),
    "black": (0,0,0), "yellow": (255,255,0), "cyan": (0,255,255), "magenta": (255,0,255),
    "orange": (255,165,0), "purple": (128,0,128), "pink": (255,192,203), "lime": (0,255,0),
    "teal": (0,128,128), "navy": (0,0,128), "maroon": (128,0,0), "olive": (128,128,0),
    "silver": (192,192,192), "gray": (128,128,128), "aqua": (0,255,255),
    "coral": (255,127,80), "salmon": (250,128,114), "gold": (255,215,0),
    "indigo": (75,0,130), "violet": (238,130,238), "brown": (165,42,42),
    "beige": (245,245,220), "ivory": (255,255,240), "lavender": (230,230,250),
    "khaki": (240,230,140), "turquoise": (64,224,208), "crimson": (220,20,60),
}


def hex_to_rgb(hex_str: str) -> tuple:
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c*2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def rgb_to_hsl(r: int, g: int, b: int) -> dict:
    h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
    return {"h": round(h*360, 1), "s": round(s*100, 1), "l": round(l*100, 1)}


def rgb_to_hsv(r: int, g: int, b: int) -> dict:
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    return {"h": round(h*360, 1), "s": round(s*100, 1), "v": round(v*100, 1)}


def rgb_to_cmyk(r: int, g: int, b: int) -> dict:
    rf, gf, bf = r/255, g/255, b/255
    k = 1 - max(rf, gf, bf)
    if k == 1:
        return {"c": 0, "m": 0, "y": 0, "k": 100}
    c = (1 - rf - k) / (1 - k)
    m = (1 - gf - k) / (1 - k)
    y = (1 - bf - k) / (1 - k)
    return {"c": round(c*100, 1), "m": round(m*100, 1), "y": round(y*100, 1), "k": round(k*100, 1)}


def rgb_to_oklch(r: int, g: int, b: int) -> dict:
    # Linear sRGB
    def lin(c):
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    rl, gl, bl = lin(r), lin(g), lin(b)
    # sRGB to OKLab (approximate)
    x = 0.4122214708*rl + 0.5363325363*gl + 0.0514459929*bl
    y = 0.2119034982*rl + 0.6806995451*gl + 0.1073969566*bl
    z = 0.0883024619*rl + 0.2817188376*gl + 0.6299787005*bl

    lc = x**0.3333333333
    mc = y**0.3333333333
    sc = z**0.3333333333

    L = 0.2104542553*lc + 0.7936177850*mc - 0.0040720468*sc
    a = 1.9779984951*lc - 2.4285922050*mc + 0.4505937099*sc
    b_ok = 0.0259040371*lc + 0.7827717662*mc - 0.8086757660*sc

    C = math.sqrt(a**2 + b_ok**2)
    H = math.degrees(math.atan2(b_ok, a)) % 360

    return {"l": round(L, 4), "c": round(C, 4), "h": round(H, 2)}


def nearest_css_name(r: int, g: int, b: int) -> str:
    best_name = "unknown"
    best_dist = float("inf")
    for name, (cr, cg, cb) in CSS_COLORS.items():
        dist = math.sqrt((r-cr)**2 + (g-cg)**2 + (b-cb)**2)
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


def _make_402(host: str, endpoint: str = "/convert") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "Color format conversion: hex, rgb, hsl, hsv, oklch, cmyk",
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
            return _make_402(request.headers.get("host", "x402-color-convert.suretat.com"))
    return await call_next(request)


class ConvertRequest(BaseModel):
    color: str
    from_format: Optional[str] = "hex"
    to: Optional[List[str]] = None


@app.get("/")
def root():
    return {"service": "x402 Color Convert", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/convert")
def convert(req: ConvertRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    color_str = req.color.strip()
    from_fmt = (req.from_format or "hex").lower()
    to_formats = [f.lower() for f in (req.to or ["rgb", "hsl", "hsv", "oklch", "cmyk", "name"])]

    # Parse input to RGB
    r = g = b = 0
    try:
        if from_fmt == "hex" or color_str.startswith("#"):
            r, g, b = hex_to_rgb(color_str)
        elif from_fmt == "rgb":
            parts = color_str.strip("rgb()").split(",")
            r, g, b = int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip())
        elif from_fmt == "name":
            name = color_str.lower()
            if name not in CSS_COLORS:
                return JSONResponse(status_code=422, content={"error": f"Unknown CSS color name: {name}"})
            r, g, b = CSS_COLORS[name]
        else:
            return JSONResponse(status_code=400, content={"error": f"Unsupported from_format: {from_fmt}"})
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Failed to parse color: {str(e)}"})

    result = {"input": color_str, "from_format": from_fmt}

    for fmt in to_formats:
        if fmt == "hex":
            result["hex"] = rgb_to_hex(r, g, b)
        elif fmt == "rgb":
            result["rgb"] = {"r": r, "g": g, "b": b, "css": f"rgb({r}, {g}, {b})"}
        elif fmt == "hsl":
            hsl = rgb_to_hsl(r, g, b)
            result["hsl"] = {**hsl, "css": f"hsl({hsl['h']}, {hsl['s']}%, {hsl['l']}%)"}
        elif fmt == "hsv":
            result["hsv"] = rgb_to_hsv(r, g, b)
        elif fmt == "oklch":
            result["oklch"] = rgb_to_oklch(r, g, b)
        elif fmt == "cmyk":
            result["cmyk"] = rgb_to_cmyk(r, g, b)
        elif fmt == "name":
            result["name"] = nearest_css_name(r, g, b)

    return result


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-color-convert.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/convert",
        "description": "Color format conversion: hex, rgb, hsl, hsv, oklch, cmyk",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3100, proxy_headers=True, forwarded_allow_ips="*")
