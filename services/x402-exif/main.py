from __future__ import annotations
import base64
import io
import os
import time
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from PIL import Image, ExifTags, TiffImagePlugin
from pydantic import BaseModel

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
MAX_MB = int(os.getenv("MAX_INPUT_MB", "20"))

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 EXIF Extractor", version="1.0.0")

# Tags EXIF utiles avec noms lisibles
INTERESTING_TAGS = {
    "Make", "Model", "Software", "DateTime", "DateTimeOriginal", "DateTimeDigitized",
    "ExposureTime", "FNumber", "ISOSpeedRatings", "ShutterSpeedValue", "ApertureValue",
    "BrightnessValue", "ExposureBiasValue", "MaxApertureValue", "MeteringMode",
    "Flash", "FocalLength", "ExifImageWidth", "ExifImageHeight",
    "ColorSpace", "WhiteBalance", "DigitalZoomRatio", "FocalLengthIn35mmFilm",
    "SceneCaptureType", "GainControl", "Contrast", "Saturation", "Sharpness",
    "GPSInfo", "LensModel", "LensMake", "LensSpecification",
    "Artist", "Copyright", "ImageDescription", "XResolution", "YResolution",
    "ResolutionUnit", "Orientation",
    "ExposureProgram", "ExposureMode", "SensingMethod", "SceneType",
}

GPS_TAGS = {
    "GPSLatitudeRef", "GPSLatitude", "GPSLongitudeRef", "GPSLongitude",
    "GPSAltitudeRef", "GPSAltitude", "GPSTimeStamp", "GPSDateStamp",
    "GPSSpeedRef", "GPSSpeed", "GPSImgDirectionRef", "GPSImgDirection",
}


def _ratio_to_float(val) -> Optional[float]:
    try:
        if hasattr(val, "numerator"):
            return round(val.numerator / val.denominator, 6) if val.denominator else None
        if isinstance(val, (int, float)):
            return float(val)
    except Exception:
        pass
    return None


def _serialize_value(val):
    if isinstance(val, (int, float, str, bool)):
        return val
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8", errors="replace")
        except Exception:
            return val.hex()
    if hasattr(val, "numerator") and hasattr(val, "denominator"):
        if val.denominator == 0:
            return None
        return round(val.numerator / val.denominator, 6)
    if isinstance(val, tuple):
        return [_serialize_value(v) for v in val]
    if isinstance(val, TiffImagePlugin.IFDRational):
        return _ratio_to_float(val)
    try:
        return str(val)
    except Exception:
        return None


def _parse_gps(gps_ifd: dict) -> Optional[dict]:
    if not gps_ifd:
        return None
    tag_name = {v: k for k, v in ExifTags.GPSTAGS.items()}

    def dms_to_dd(dms, ref):
        try:
            d = _ratio_to_float(dms[0]) or 0
            m = _ratio_to_float(dms[1]) or 0
            s = _ratio_to_float(dms[2]) or 0
            dd = d + m / 60 + s / 3600
            if ref in ("S", "W"):
                dd = -dd
            return round(dd, 7)
        except Exception:
            return None

    gps: dict = {}
    lat_raw = gps_ifd.get(tag_name.get("GPSLatitude"))
    lat_ref = gps_ifd.get(tag_name.get("GPSLatitudeRef"))
    lon_raw = gps_ifd.get(tag_name.get("GPSLongitude"))
    lon_ref = gps_ifd.get(tag_name.get("GPSLongitudeRef"))
    alt_raw = gps_ifd.get(tag_name.get("GPSAltitude"))

    if lat_raw and lat_ref:
        gps["latitude"] = dms_to_dd(lat_raw, lat_ref)
        gps["latitude_ref"] = lat_ref
    if lon_raw and lon_ref:
        gps["longitude"] = dms_to_dd(lon_raw, lon_ref)
        gps["longitude_ref"] = lon_ref
    if alt_raw is not None:
        gps["altitude_m"] = _ratio_to_float(alt_raw)
    if gps.get("latitude") and gps.get("longitude"):
        gps["maps_url"] = f"https://maps.google.com/?q={gps['latitude']},{gps['longitude']}"

    # Timestamp GPS
    ts = gps_ifd.get(tag_name.get("GPSTimeStamp"))
    ds = gps_ifd.get(tag_name.get("GPSDateStamp"))
    if ts:
        try:
            h, m, s = [_ratio_to_float(x) or 0 for x in ts]
            gps["timestamp_utc"] = f"{int(h):02d}:{int(m):02d}:{s:.2f}"
        except Exception:
            pass
    if ds:
        gps["date"] = ds

    return gps if gps else None


def _extract_exif(img_bytes: bytes) -> dict:
    img = Image.open(io.BytesIO(img_bytes))

    base_info = {
        "format": img.format,
        "mode": img.mode,
        "width": img.size[0],
        "height": img.size[1],
        "size_bytes": len(img_bytes),
    }

    raw_exif = img.getexif()
    if not raw_exif:
        return {**base_info, "exif": None, "gps": None, "has_exif": False}

    exif: dict = {}
    gps_data = None

    for tag_id, value in raw_exif.items():
        tag = ExifTags.TAGS.get(tag_id, str(tag_id))
        if tag == "GPSInfo":
            try:
                gps_ifd = raw_exif.get_ifd(tag_id)
                gps_data = _parse_gps(gps_ifd)
            except Exception:
                pass
            continue
        if tag in INTERESTING_TAGS:
            serialized = _serialize_value(value)
            if serialized is not None:
                exif[tag] = serialized

    # Vitesse d'obturation lisible
    if "ExposureTime" in exif and isinstance(exif["ExposureTime"], float):
        et = exif["ExposureTime"]
        if et < 1:
            exif["ExposureTime_readable"] = f"1/{round(1/et)}"
        else:
            exif["ExposureTime_readable"] = f"{et:.1f}s"

    return {
        **base_info,
        "has_exif": bool(exif),
        "exif": exif if exif else None,
        "gps": gps_data,
    }


def _make_402(host: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "x402Version": 1, "error": "Payment required",
            "accepts": [{
                "scheme": "exact", "network": NETWORK,
                "maxAmountRequired": PRICE_ATOMIC,
                "resource": f"https://{host}/extract",
                "description": "Extraction des métadonnées EXIF d'une image (URL ou base64)",
                "mimeType": "application/json",
                "payTo": PAY_TO, "maxTimeoutSeconds": 300,
                "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
            }],
        },
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/extract" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-exif.suretat.com"))
    return await call_next(request)


class ExifRequest(BaseModel):
    image_url: Optional[str] = None
    image_base64: Optional[str] = None


@app.get("/")
def root():
    return {
        "service": "x402 EXIF Extractor",
        "protocol": "x402 (Base/USDC)",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/image",
        "endpoint": "POST /extract",
        "body": {"image_url": "https://example.com/photo.jpg"},
        "body_alt": {"image_base64": "BASE64_ENCODED_IMAGE"},
        "extracts": ["Make/Model", "DateTimeOriginal", "GPS coords + maps_url", "Exposure settings", "Lens info"],
        "formats": ["JPEG", "TIFF", "PNG", "HEIC"],
        "docs": "/docs",
    }


@app.post("/extract")
async def extract(req: ExifRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if not req.image_url and not req.image_base64:
        return JSONResponse(status_code=422, content={"error": "image_url ou image_base64 requis"})

    if req.image_base64:
        try:
            img_bytes = base64.b64decode(req.image_base64)
        except Exception:
            return JSONResponse(status_code=422, content={"error": "base64 invalide"})
    else:
        if not req.image_url.startswith(("http://", "https://")):
            return JSONResponse(status_code=422, content={"error": "URL invalide"})
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(req.image_url, follow_redirects=True)
                img_bytes = resp.content
        except httpx.TimeoutException:
            return JSONResponse(status_code=504, content={"error": "Timeout lors du téléchargement"})
        except Exception as e:
            return JSONResponse(status_code=502, content={"error": f"Téléchargement échoué : {e}"})

    if len(img_bytes) > MAX_MB * 1024 * 1024:
        return JSONResponse(status_code=413, content={"error": f"Image trop grande (max {MAX_MB} MB)"})

    try:
        result = _extract_exif(img_bytes)
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Impossible de lire l'image : {e}"})

    if req.image_url:
        result["source_url"] = req.image_url

    return result


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-exif.suretat.com")
    return {"x402Version": 1, "accepts": [{
        "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"https://{host}/extract",
        "description": "Extraction des métadonnées EXIF d'une image",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
    }]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3093, proxy_headers=True, forwarded_allow_ips="*")
