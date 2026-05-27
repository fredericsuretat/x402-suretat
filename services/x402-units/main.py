import os
import json
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field

FACILITATOR_URL = os.getenv("FACILITATOR_URL", "https://api.cdp.coinbase.com/platform/v2/x402")
PAY_TO = os.getenv("PAY_TO_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
USDC_ADDRESS = os.getenv("USDC_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
NETWORK = os.getenv("NETWORK", "base")

app = FastAPI(title="x402 Unit Converter", version="1.0.0")

PAYMENT_INFO = {
    "x402Version": 1,
    "accepts": [{
        "scheme": "exact",
        "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"http://{os.getenv('HOST', 'localhost')}:{os.getenv('PORT', '3064')}/convert",
        "description": "Unit Converter",
        "mimeType": "application/json",
        "payTo": PAY_TO,
        "maxTimeoutSeconds": 300,
        "asset": USDC_ADDRESS,
        "extra": {"name": "USD Coin", "version": "2"}
    }]
}

def verify_payment(request: Request) -> bool:
    token = request.headers.get("X-PAYMENT") or request.headers.get("x-payment", "")
    return bool(token)

# All conversions store base unit and factor TO base unit
CATEGORIES = {
    "longueur": {
        "base": "mètre",
        "unites": {
            "millimetre": 0.001, "mm": 0.001,
            "centimetre": 0.01, "cm": 0.01,
            "decimetre": 0.1, "dm": 0.1,
            "metre": 1.0, "m": 1.0,
            "kilometre": 1000.0, "km": 1000.0,
            "pouce": 0.0254, "inch": 0.0254, "in": 0.0254,
            "pied": 0.3048, "foot": 0.3048, "feet": 0.3048, "ft": 0.3048,
            "yard": 0.9144, "yd": 0.9144,
            "mile": 1609.344, "mi": 1609.344,
            "mille_marin": 1852.0, "nm": 1852.0,
            "lieue": 4000.0,
        }
    },
    "masse": {
        "base": "kilogramme",
        "unites": {
            "milligramme": 0.000001, "mg": 0.000001,
            "gramme": 0.001, "g": 0.001,
            "kilogramme": 1.0, "kg": 1.0,
            "tonne": 1000.0, "t": 1000.0,
            "livre": 0.45359237, "pound": 0.45359237, "lb": 0.45359237, "lbs": 0.45359237,
            "once": 0.028349523, "ounce": 0.028349523, "oz": 0.028349523,
            "stone": 6.35029318, "st": 6.35029318,
            "carat": 0.0002, "ct": 0.0002,
            "quintal": 100.0, "q": 100.0,
        }
    },
    "volume": {
        "base": "litre",
        "unites": {
            "millilitre": 0.001, "ml": 0.001,
            "centilitre": 0.01, "cl": 0.01,
            "decilitre": 0.1, "dl": 0.1,
            "litre": 1.0, "l": 1.0,
            "metre_cube": 1000.0, "m3": 1000.0,
            "gallon_us": 3.785411784, "gal": 3.785411784,
            "gallon_uk": 4.54609, "gal_uk": 4.54609,
            "pinte_us": 0.473176473, "pint": 0.473176473,
            "tasse": 0.23658824, "cup": 0.23658824,
            "fluid_ounce": 0.029573530, "fl_oz": 0.029573530,
            "cuillere_soupe": 0.014786765, "tbsp": 0.014786765,
            "cuillere_cafe": 0.004928922, "tsp": 0.004928922,
        }
    },
    "surface": {
        "base": "mètre carré",
        "unites": {
            "millimetre_carre": 0.000001, "mm2": 0.000001,
            "centimetre_carre": 0.0001, "cm2": 0.0001,
            "metre_carre": 1.0, "m2": 1.0,
            "are": 100.0,
            "hectare": 10000.0, "ha": 10000.0,
            "kilometre_carre": 1000000.0, "km2": 1000000.0,
            "pied_carre": 0.09290304, "ft2": 0.09290304,
            "yard_carre": 0.83612736, "yd2": 0.83612736,
            "acre": 4046.8564224,
            "mile_carre": 2589988.110336, "mi2": 2589988.110336,
        }
    },
    "vitesse": {
        "base": "mètre/seconde",
        "unites": {
            "metre_seconde": 1.0, "m/s": 1.0, "ms": 1.0,
            "kilometre_heure": 0.27777778, "km/h": 0.27777778, "kmh": 0.27777778,
            "mile_heure": 0.44704, "mph": 0.44704,
            "noeud": 0.51444444, "knot": 0.51444444, "kt": 0.51444444,
            "pied_seconde": 0.3048, "ft/s": 0.3048,
            "mach": 340.29,
        }
    },
    "pression": {
        "base": "pascal",
        "unites": {
            "pascal": 1.0, "pa": 1.0,
            "kilopascal": 1000.0, "kpa": 1000.0,
            "megapascal": 1000000.0, "mpa": 1000000.0,
            "bar": 100000.0,
            "millibar": 100.0, "mbar": 100.0, "hpa": 100.0,
            "atmosphere": 101325.0, "atm": 101325.0,
            "psi": 6894.757,
            "mmhg": 133.322, "torr": 133.322,
        }
    },
    "energie": {
        "base": "joule",
        "unites": {
            "joule": 1.0, "j": 1.0,
            "kilojoule": 1000.0, "kj": 1000.0,
            "megajoule": 1000000.0, "mj": 1000000.0,
            "calorie": 4.184, "cal": 4.184,
            "kilocalorie": 4184.0, "kcal": 4184.0,
            "kwh": 3600000.0, "kilowatt_heure": 3600000.0,
            "wh": 3600.0, "watt_heure": 3600.0,
            "btu": 1055.05585,
            "electronvolt": 1.60218e-19, "ev": 1.60218e-19,
            "erg": 1e-7,
        }
    },
    "stockage": {
        "base": "octet",
        "unites": {
            "bit": 0.125, "b": 0.125,
            "octet": 1.0, "byte": 1.0,
            "kilooctet": 1024.0, "ko": 1024.0, "kb": 1024.0,
            "megaoctet": 1048576.0, "mo": 1048576.0, "mb": 1048576.0,
            "gigaoctet": 1073741824.0, "go": 1073741824.0, "gb": 1073741824.0,
            "teraoctet": 1099511627776.0, "to": 1099511627776.0, "tb": 1099511627776.0,
            "petaoctet": 1125899906842624.0, "po": 1125899906842624.0, "pb": 1125899906842624.0,
            "kio": 1024.0, "mio": 1048576.0, "gio": 1073741824.0, "tio": 1099511627776.0,
        }
    },
}

def convert_temp(value: float, from_u: str, to_u: str) -> float:
    u_map = {"celsius": "c", "centigrade": "c", "c": "c",
             "fahrenheit": "f", "f": "f",
             "kelvin": "k", "k": "k",
             "rankine": "r", "r": "r"}
    from_u = u_map.get(from_u.lower())
    to_u = u_map.get(to_u.lower())
    if not from_u or not to_u:
        raise ValueError(f"Unité de température inconnue")
    # First convert to Celsius
    if from_u == "c":
        c = value
    elif from_u == "f":
        c = (value - 32) * 5 / 9
    elif from_u == "k":
        c = value - 273.15
    elif from_u == "r":
        c = (value - 491.67) * 5 / 9
    # Then to target
    if to_u == "c":
        return c
    elif to_u == "f":
        return c * 9 / 5 + 32
    elif to_u == "k":
        return c + 273.15
    elif to_u == "r":
        return (c + 273.15) * 9 / 5

class ConvertRequest(BaseModel):
    valeur: float
    de: str = Field(description="Unité source")
    vers: str = Field(description="Unité cible")
    categorie: str | None = Field(default=None, description="Catégorie (optionnel, auto-détectée)")
    precision: int = Field(default=6, ge=0, le=15)

@app.get("/")
def info():
    return {
        "service": "x402 Unit Converter",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/conversion",
        "endpoint": "POST /convert",
        "categories": list(CATEGORIES.keys()) + ["temperature"],
        "docs": "/docs",
        "tagline": "Convert units — length, weight, temperature, pressure, speed and more",
        "curl_example": "curl https://x402-units.suretat.com/convert -H 'Content-Type: application/json' -d '{\"value\": 100, \"from\": \"km\", \"to\": \"miles\"}'",
        "try_it": "https://x402-units.suretat.com/docs",
    }

@app.post("/convert")
async def convert(req: Request, body: ConvertRequest):
    if not verify_payment(req):
        return Response(
            content=json.dumps({"error": "Payment required", "x402": PAYMENT_INFO}),
            status_code=402,
            media_type="application/json",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-ACCEPTS-PAYMENT": "x402"}
        )

    from_u = body.de.lower().strip()
    to_u = body.vers.lower().strip()

    # Temperature is special
    temp_units = {"celsius", "centigrade", "c", "fahrenheit", "f", "kelvin", "k", "rankine", "r"}
    if from_u in temp_units or to_u in temp_units:
        try:
            result = convert_temp(body.valeur, from_u, to_u)
            return {
                "valeur": body.valeur,
                "de": body.de,
                "vers": body.vers,
                "resultat": round(result, body.precision),
                "categorie": "temperature"
            }
        except ValueError as e:
            return {"error": str(e)}

    # Find category
    cat_name = body.categorie.lower() if body.categorie else None
    found_cat = None
    from_factor = None
    to_factor = None

    if cat_name and cat_name in CATEGORIES:
        cat = CATEGORIES[cat_name]
        from_factor = cat["unites"].get(from_u)
        to_factor = cat["unites"].get(to_u)
        if from_factor and to_factor:
            found_cat = cat_name

    if not found_cat:
        for name, cat in CATEGORIES.items():
            f = cat["unites"].get(from_u)
            t = cat["unites"].get(to_u)
            if f and t:
                from_factor = f
                to_factor = t
                found_cat = name
                break

    if not found_cat:
        return {"error": f"Unités inconnues ou incompatibles: '{body.de}' → '{body.vers}'",
                "categories_disponibles": list(CATEGORIES.keys()) + ["temperature"]}

    result = body.valeur * from_factor / to_factor
    return {
        "valeur": body.valeur,
        "de": body.de,
        "vers": body.vers,
        "resultat": round(result, body.precision),
        "categorie": found_cat,
        "facteur": from_factor / to_factor
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
            "description": "x402 Unit Converter",
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

