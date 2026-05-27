import os
import json
import math
import colorsys
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
USDC_ADDRESS = os.getenv("USDC_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
NETWORK = os.getenv("NETWORK", "base")

app = FastAPI(title="x402 Color Converter", version="1.0.0")

PAYMENT_INFO = {
    "x402Version": 1,
    "accepts": [{
        "scheme": "exact",
        "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"http://{os.getenv('HOST', 'localhost')}:{os.getenv('PORT', '3068')}/convert",
        "description": "Color Converter (HEX/RGB/HSL/HSV/CMYK)",
        "mimeType": "application/json",
        "payTo": PAY_TO,
        "maxTimeoutSeconds": 300,
        "asset": USDC_ADDRESS,
        "extra": {"name": "USD Coin", "version": "2"}
    }]
}

def verify_payment(request: Request) -> bool:
    return bool(request.headers.get("X-PAYMENT") or request.headers.get("x-payment", ""))

# Basic named colors (CSS Level 1 + common FR names)
NAMED_COLORS = {
    "rouge": "#FF0000", "red": "#FF0000",
    "vert": "#008000", "green": "#008000",
    "bleu": "#0000FF", "blue": "#0000FF",
    "blanc": "#FFFFFF", "white": "#FFFFFF",
    "noir": "#000000", "black": "#000000",
    "jaune": "#FFFF00", "yellow": "#FFFF00",
    "cyan": "#00FFFF", "aqua": "#00FFFF",
    "magenta": "#FF00FF", "fuchsia": "#FF00FF",
    "orange": "#FFA500",
    "rose": "#FFC0CB", "pink": "#FFC0CB",
    "violet": "#EE82EE",
    "pourpre": "#800080", "purple": "#800080",
    "marron": "#A52A2A", "brown": "#A52A2A",
    "gris": "#808080", "grey": "#808080", "gray": "#808080",
    "argent": "#C0C0C0", "silver": "#C0C0C0",
    "or": "#FFD700", "gold": "#FFD700",
    "turquoise": "#40E0D0",
    "indigo": "#4B0082",
    "beige": "#F5F5DC",
    "ivoire": "#FFFFF0", "ivory": "#FFFFF0",
    "lavande": "#E6E6FA", "lavender": "#E6E6FA",
    "lilas": "#C8A2C8",
    "saumon": "#FA8072", "salmon": "#FA8072",
    "corail": "#FF7F50", "coral": "#FF7F50",
    "lime": "#00FF00",
    "navy": "#000080", "marine": "#000080",
    "teal": "#008080",
    "olive": "#808000",
    "crimson": "#DC143C",
    "transparent": "#00000000",
}

def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c*2 for c in h)
    if len(h) != 6:
        raise ValueError(f"Format hex invalide: #{h}")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"

def rgb_to_hsl(r: int, g: int, b: int) -> tuple[float, float, float]:
    h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
    return round(h * 360, 1), round(s * 100, 1), round(l * 100, 1)

def hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb(h/360, l/100, s/100)
    return round(r*255), round(g*255), round(b*255)

def rgb_to_hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    return round(h*360, 1), round(s*100, 1), round(v*100, 1)

def rgb_to_cmyk(r: int, g: int, b: int) -> tuple[float, float, float, float]:
    if r == g == b == 0:
        return 0.0, 0.0, 0.0, 100.0
    r_, g_, b_ = r/255, g/255, b/255
    k = 1 - max(r_, g_, b_)
    if k == 1:
        return 0.0, 0.0, 0.0, 100.0
    c = (1 - r_ - k) / (1 - k)
    m = (1 - g_ - k) / (1 - k)
    y = (1 - b_ - k) / (1 - k)
    return round(c*100, 1), round(m*100, 1), round(y*100, 1), round(k*100, 1)

def luminance(r: int, g: int, b: int) -> float:
    def lin(c):
        c /= 255
        return c/12.92 if c <= 0.03928 else ((c+0.055)/1.055)**2.4
    return 0.2126*lin(r) + 0.7152*lin(g) + 0.0722*lin(b)

def contrast_ratio(r1: int, g1: int, b1: int, r2: int = 255, g2: int = 255, b2: int = 255) -> float:
    l1 = luminance(r1, g1, b1)
    l2 = luminance(r2, g2, b2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)

def wcag_level(ratio: float) -> str:
    if ratio >= 7:
        return "AAA"
    if ratio >= 4.5:
        return "AA"
    if ratio >= 3:
        return "AA (grand texte)"
    return "Insuffisant"

def build_all_formats(r: int, g: int, b: int) -> dict:
    h_hsl, s_hsl, l_hsl = rgb_to_hsl(r, g, b)
    h_hsv, s_hsv, v_hsv = rgb_to_hsv(r, g, b)
    c, m, y, k = rgb_to_cmyk(r, g, b)
    ratio = contrast_ratio(r, g, b)
    return {
        "hex": rgb_to_hex(r, g, b),
        "hex_lower": rgb_to_hex(r, g, b).lower(),
        "rgb": {"r": r, "g": g, "b": b},
        "rgb_css": f"rgb({r}, {g}, {b})",
        "hsl": {"h": h_hsl, "s": s_hsl, "l": l_hsl},
        "hsl_css": f"hsl({h_hsl}, {s_hsl}%, {l_hsl}%)",
        "hsv": {"h": h_hsv, "s": s_hsv, "v": v_hsv},
        "cmyk": {"c": c, "m": m, "y": y, "k": k},
        "cmyk_pourcent": f"cmyk({c}%, {m}%, {y}%, {k}%)",
        "luminance": round(luminance(r, g, b), 4),
        "contraste_vs_blanc": ratio,
        "wcag_vs_blanc": wcag_level(ratio),
        "contraste_vs_noir": round(contrast_ratio(0, 0, 0, r, g, b), 2),
        "wcag_vs_noir": wcag_level(round(contrast_ratio(0, 0, 0, r, g, b), 2)),
    }

class ColorRequest(BaseModel):
    couleur: str = Field(description="Couleur en HEX (#FF5733), RGB (255,87,51), HSL (9,100,60), ou nom (rouge, red...)")

@app.get("/")
def info():
    return {
        "service": "x402 Color Converter",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/conversion",
        "endpoint": "POST /convert",
        "formats_entree": ["HEX (#RRGGBB, #RGB)", "rgb(R,G,B)", "hsl(H,S,L)", "nom (rouge, blue...)"],
        "formats_sortie": ["HEX", "RGB", "HSL", "HSV", "CMYK", "luminance WCAG"],
        "docs": "/docs",
        "tagline": "Convert colors between HEX, RGB, HSL, CMYK — get complementary and luminance",
        "curl_example": "curl https://x402-color.suretat.com/convert -H 'Content-Type: application/json' -d '{\"color\": \"#ff6b6b\", \"formats\": [\"rgb\", \"hsl\"]}'",
        "try_it": "https://x402-color.suretat.com/docs",
    }

@app.post("/convert")
async def convert(req: Request, body: ColorRequest):
    if not verify_payment(req):
        return Response(content=json.dumps({"error": "Payment required", "x402": PAYMENT_INFO}),
                        status_code=402, media_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-ACCEPTS-PAYMENT": "x402"})
    c = body.couleur.strip()

    # Named color
    if c.lower() in NAMED_COLORS:
        c = NAMED_COLORS[c.lower()]

    # HEX
    if c.startswith("#") or (len(c) in (3, 6) and all(x in "0123456789abcdefABCDEF" for x in c)):
        try:
            r, g, b = hex_to_rgb(c if c.startswith("#") else f"#{c}")
            return {"entree": body.couleur, "format_detecte": "HEX"} | build_all_formats(r, g, b)
        except ValueError as e:
            return {"error": str(e)}

    # rgb(R, G, B) or R,G,B
    import re
    rgb_match = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", c, re.I) or \
                re.match(r"^(\d+)\s*,\s*(\d+)\s*,\s*(\d+)$", c)
    if rgb_match:
        r, g, b = [int(x) for x in rgb_match.groups()]
        if not all(0 <= v <= 255 for v in (r, g, b)):
            return {"error": "Valeurs RGB hors plage 0-255"}
        return {"entree": body.couleur, "format_detecte": "RGB"} | build_all_formats(r, g, b)

    # hsl(H, S%, L%)
    hsl_match = re.match(r"hsl\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)%?\s*,\s*(\d+(?:\.\d+)?)%?\s*\)", c, re.I) or \
                re.match(r"^(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)$", c)
    if hsl_match:
        h, s, l = [float(x) for x in hsl_match.groups()]
        r, g, b = hsl_to_rgb(h, s, l)
        return {"entree": body.couleur, "format_detecte": "HSL"} | build_all_formats(r, g, b)

    return {"error": f"Format non reconnu: '{body.couleur}'. Essayez: '#FF5733', 'rgb(255,87,51)', 'hsl(9,100%,60%)', ou un nom de couleur"}

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
            "description": "x402 Color Converter",
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

