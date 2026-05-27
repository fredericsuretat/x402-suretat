from __future__ import annotations
import base64
import logging
import os
import time
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field

log = logging.getLogger("x402-screenshot")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "2000")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
TIMEOUT_MS    = int(os.getenv("PAGE_TIMEOUT_MS", "30000"))

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Screenshot", version="1.0.0")


class ScreenshotRequest(BaseModel):
    url: str = Field(..., description="URL to screenshot")
    format: Literal["png", "jpeg", "pdf"] = Field(default="png", description="Output format")
    width: int = Field(default=1280, ge=320, le=3840, description="Viewport width in pixels")
    height: int = Field(default=720, ge=240, le=2160, description="Viewport height in pixels")
    full_page: bool = Field(default=False, description="Capture the full scrollable page")
    wait_for: Literal["load", "domcontentloaded", "networkidle"] = Field(
        default="networkidle", description="Event to wait for before capturing"
    )
    delay_ms: int = Field(default=0, ge=0, le=5000, description="Extra delay in ms after load")
    dark_mode: bool = Field(default=False, description="Emulate dark mode (prefers-color-scheme: dark)")
    device_scale: float = Field(default=1.0, ge=1.0, le=3.0, description="Device pixel ratio (1=desktop, 2=retina)")
    selector: str | None = Field(default=None, description="CSS selector to screenshot just that element")
    javascript: str | None = Field(default=None, description="JavaScript to execute before screenshot")


@app.get("/")
def root():
    return {
        "service": "x402 Screenshot",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoint": "POST /screenshot",
        "tagline": "Take full-page or viewport screenshots of any URL — PNG, JPEG, or PDF via Playwright",
        "curl_example": "curl https://x402-screenshot.suretat.com/screenshot -H 'Content-Type: application/json' -d '{\"url\": \"https://example.com\", \"format\": \"png\", \"full_page\": false}'",
        "try_it": "https://x402-screenshot.suretat.com/docs",
        "docs": "/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/screenshot" and request.method == "POST":
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
                        "resource": "https://" + request.headers.get("host", "") + "/screenshot",
                        "description": "Webpage screenshot — PNG, JPEG or PDF",
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


@app.post("/screenshot")
async def screenshot(req: ScreenshotRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(
                viewport={"width": req.width, "height": req.height},
                device_scale_factor=req.device_scale,
                color_scheme="dark" if req.dark_mode else "light",
            )
            page = await context.new_page()

            try:
                await page.goto(req.url, wait_until=req.wait_for, timeout=TIMEOUT_MS)
            except Exception as e:
                await browser.close()
                return JSONResponse(status_code=502, content={"error": f"Navigation failed: {e}"})

            if req.delay_ms > 0:
                await page.wait_for_timeout(req.delay_ms)

            if req.javascript:
                await page.evaluate(req.javascript)

            if req.format == "pdf":
                pdf_bytes = await page.pdf(
                    format="A4",
                    print_background=True,
                )
                await browser.close()
                return {
                    "format": "pdf",
                    "url": req.url,
                    "base64": base64.b64encode(pdf_bytes).decode(),
                    "size_bytes": len(pdf_bytes),
                }

            target = page
            if req.selector:
                target = await page.query_selector(req.selector)
                if not target:
                    await browser.close()
                    return JSONResponse(status_code=404, content={"error": f"Selector not found: {req.selector}"})

            img_bytes = await target.screenshot(
                type=req.format,
                full_page=req.full_page if not req.selector else False,
                quality=85 if req.format == "jpeg" else None,
            )
            await browser.close()

        return {
            "format": req.format,
            "url": req.url,
            "width": req.width,
            "height": req.height,
            "full_page": req.full_page,
            "base64": base64.b64encode(img_bytes).decode(),
            "size_bytes": len(img_bytes),
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-screenshot.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/screenshot",
            "description": "Webpage screenshot — PNG, JPEG or PDF",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3075, proxy_headers=True, forwarded_allow_ips="*")
