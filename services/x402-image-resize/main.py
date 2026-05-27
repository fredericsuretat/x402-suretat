from __future__ import annotations
import base64
import io
import logging
import os
import time
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
from pydantic import BaseModel, Field

log = logging.getLogger("x402-image-resize")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
MAX_INPUT_MB  = int(os.getenv("MAX_INPUT_MB", "20"))

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Image Resize & Convert", version="1.0.0")

OutputFormat = Literal["jpeg", "png", "webp", "gif", "bmp", "tiff"]


class ResizeOp(BaseModel):
    type: Literal["resize"] = "resize"
    width: int | None = Field(default=None, ge=1, le=8000)
    height: int | None = Field(default=None, ge=1, le=8000)
    keep_aspect: bool = Field(default=True)


class CropOp(BaseModel):
    type: Literal["crop"] = "crop"
    left: int = Field(..., ge=0)
    top: int = Field(..., ge=0)
    right: int = Field(..., ge=1)
    bottom: int = Field(..., ge=1)


class RotateOp(BaseModel):
    type: Literal["rotate"] = "rotate"
    degrees: float = Field(..., description="Degrees clockwise")
    expand: bool = Field(default=True)


class FlipOp(BaseModel):
    type: Literal["flip"] = "flip"
    direction: Literal["horizontal", "vertical"]


class BrightnessOp(BaseModel):
    type: Literal["brightness"] = "brightness"
    factor: float = Field(..., ge=0.0, le=4.0, description="1.0 = original, 0.5 = darker, 2.0 = brighter")


class ContrastOp(BaseModel):
    type: Literal["contrast"] = "contrast"
    factor: float = Field(..., ge=0.0, le=4.0)


class BlurOp(BaseModel):
    type: Literal["blur"] = "blur"
    radius: float = Field(default=2.0, ge=0.1, le=20.0)


class GrayscaleOp(BaseModel):
    type: Literal["grayscale"] = "grayscale"


class ThumbnailOp(BaseModel):
    type: Literal["thumbnail"] = "thumbnail"
    max_size: int = Field(default=256, ge=16, le=2000)


class ImageProcessRequest(BaseModel):
    image_base64: str = Field(..., description="Base64-encoded input image")
    operations: list[ResizeOp | CropOp | RotateOp | FlipOp | BrightnessOp | ContrastOp | BlurOp | GrayscaleOp | ThumbnailOp] = Field(
        default=[], description="Operations to apply in order"
    )
    output_format: OutputFormat = Field(default="jpeg", description="Output image format")
    quality: int = Field(default=85, ge=1, le=100, description="Quality for JPEG/WebP (1-100)")
    strip_metadata: bool = Field(default=True, description="Remove EXIF and other metadata")


@app.get("/")
def root():
    return {
        "service": "x402 Image Resize & Convert",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoint": "POST /process",
        "operations": ["resize", "crop", "rotate", "flip", "brightness", "contrast", "blur", "grayscale", "thumbnail"],
        "tagline": "Resize, crop, convert and filter images — JPEG, PNG, WebP, GIF, TIFF",
        "curl_example": "curl https://x402-image-resize.suretat.com/process -H 'Content-Type: application/json' -d '{\"image_base64\": \"BASE64\", \"operations\": [{\"type\": \"resize\", \"width\": 800}], \"output_format\": \"webp\"}'",
        "try_it": "https://x402-image-resize.suretat.com/docs",
        "docs": "/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/process" and request.method == "POST":
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
                        "resource": "https://" + request.headers.get("host", "") + "/process",
                        "description": "Image resize, convert and filter",
                        "mimeType": "application/json",
                        "payTo": PAY_TO,
                        "maxTimeoutSeconds": 300,
                        "asset": ASSET_ADDRESS,
                        "extra": {"name": "USDC", "version": "2"},
                    }],
                },
                headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
            )
    return await call_next(request)


@app.post("/process")
def process_image(req: ImageProcessRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        img_bytes = base64.b64decode(req.image_base64)
        if len(img_bytes) > MAX_INPUT_MB * 1024 * 1024:
            return JSONResponse(status_code=413, content={"error": f"Image too large (max {MAX_INPUT_MB} MB)"})
        img = Image.open(io.BytesIO(img_bytes))
        original_format = img.format or "JPEG"
        original_size = img.size
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Invalid image: {e}"})

    for op in req.operations:
        if op.type == "resize":
            w, h = op.width or img.size[0], op.height or img.size[1]
            if op.keep_aspect:
                img.thumbnail((w, h), Image.LANCZOS)
            else:
                img = img.resize((w, h), Image.LANCZOS)
        elif op.type == "crop":
            img = img.crop((op.left, op.top, op.right, op.bottom))
        elif op.type == "rotate":
            img = img.rotate(-op.degrees, expand=op.expand, resample=Image.BICUBIC)
        elif op.type == "flip":
            img = ImageOps.mirror(img) if op.direction == "horizontal" else ImageOps.flip(img)
        elif op.type == "brightness":
            img = ImageEnhance.Brightness(img).enhance(op.factor)
        elif op.type == "contrast":
            img = ImageEnhance.Contrast(img).enhance(op.factor)
        elif op.type == "blur":
            img = img.filter(ImageFilter.GaussianBlur(radius=op.radius))
        elif op.type == "grayscale":
            img = ImageOps.grayscale(img)
        elif op.type == "thumbnail":
            img.thumbnail((op.max_size, op.max_size), Image.LANCZOS)

    out_fmt = req.output_format.upper()
    if out_fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")

    out_buf = io.BytesIO()
    save_kwargs: dict = {}
    if out_fmt in ("JPEG", "WEBP"):
        save_kwargs["quality"] = req.quality
    if req.strip_metadata and out_fmt == "JPEG":
        save_kwargs["exif"] = b""

    img.save(out_buf, format=out_fmt, **save_kwargs)
    out_bytes = out_buf.getvalue()

    return {
        "output_format": req.output_format,
        "original_size": {"width": original_size[0], "height": original_size[1]},
        "output_size": {"width": img.size[0], "height": img.size[1]},
        "original_bytes": len(img_bytes),
        "output_bytes": len(out_bytes),
        "compression_ratio": round(len(out_bytes) / len(img_bytes), 3),
        "image_base64": base64.b64encode(out_bytes).decode(),
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-image-resize.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/process",
            "description": "Image resize, convert and filter",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3076, proxy_headers=True, forwarded_allow_ips="*")
