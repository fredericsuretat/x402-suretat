from __future__ import annotations
import os, time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime, date, timedelta
import math

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Date Calc", version="1.0.0")

WEEKDAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin",
             "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def _make_402(host: str, endpoint: str = "/calculate") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "Date calculations: diff, add, weekday, format",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/calculate" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-date-calc.suretat.com"))
    return await call_next(request)


class CalcRequest(BaseModel):
    mode: str
    date1: Optional[str] = None
    date2: Optional[str] = None
    date: Optional[str] = None
    days: Optional[int] = None
    months: Optional[int] = None
    years: Optional[int] = None
    locale: Optional[str] = "en"


def parse_date(s: str) -> date:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {s}")


@app.get("/")
def root():
    return {"service": "x402 Date Calc", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/calculate")
def calculate(req: CalcRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    mode = req.mode.lower()

    if mode == "diff":
        if not req.date1 or not req.date2:
            return JSONResponse(status_code=400, content={"error": "date1 and date2 required for diff mode"})
        try:
            d1 = parse_date(req.date1)
            d2 = parse_date(req.date2)
        except ValueError as e:
            return JSONResponse(status_code=422, content={"error": str(e)})

        delta = d2 - d1
        total_days = abs(delta.days)
        years = total_days // 365
        remaining = total_days % 365
        months = remaining // 30
        days = remaining % 30

        return {
            "date1": str(d1),
            "date2": str(d2),
            "total_days": delta.days,
            "absolute_days": total_days,
            "years": years,
            "months": months,
            "days": days,
            "is_future": delta.days > 0,
        }

    elif mode == "add":
        if not req.date:
            return JSONResponse(status_code=400, content={"error": "date required for add mode"})
        try:
            d = parse_date(req.date)
        except ValueError as e:
            return JSONResponse(status_code=422, content={"error": str(e)})

        days_to_add = req.days or 0
        months_to_add = req.months or 0
        years_to_add = req.years or 0

        result = d + timedelta(days=days_to_add)
        # Add months and years
        month = result.month + months_to_add
        year = result.year + years_to_add + (month - 1) // 12
        month = (month - 1) % 12 + 1
        try:
            result = result.replace(year=year, month=month)
        except ValueError:
            # Day out of range for month, use last day
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            result = result.replace(year=year, month=month, day=last_day)

        return {
            "original": str(d),
            "result": str(result),
            "added": {"days": days_to_add, "months": months_to_add, "years": years_to_add},
        }

    elif mode == "weekday":
        if not req.date:
            return JSONResponse(status_code=400, content={"error": "date required for weekday mode"})
        try:
            d = parse_date(req.date)
        except ValueError as e:
            return JSONResponse(status_code=422, content={"error": str(e)})

        wd = d.weekday()
        return {
            "date": str(d),
            "weekday_en": WEEKDAYS_EN[wd],
            "weekday_fr": WEEKDAYS_FR[wd],
            "weekday_number": wd + 1,  # 1=Monday
            "is_weekend": wd >= 5,
            "week_number": d.isocalendar()[1],
        }

    elif mode == "format":
        if not req.date:
            return JSONResponse(status_code=400, content={"error": "date required for format mode"})
        try:
            d = parse_date(req.date)
        except ValueError as e:
            return JSONResponse(status_code=422, content={"error": str(e)})

        locale = (req.locale or "en").lower()
        if locale == "fr":
            wd_fr = WEEKDAYS_FR[d.weekday()]
            month_fr = MONTHS_FR[d.month - 1]
            formatted = f"{d.day} {month_fr} {d.year}"
            formatted_long = f"{wd_fr} {d.day} {month_fr} {d.year}"
        else:
            wd_en = WEEKDAYS_EN[d.weekday()]
            formatted = d.strftime("%B %d, %Y")
            formatted_long = d.strftime(f"{wd_en}, %B %d, %Y")

        return {
            "date": str(d),
            "locale": locale,
            "formatted": formatted,
            "formatted_long": formatted_long,
            "iso8601": str(d),
        }

    else:
        return JSONResponse(status_code=400, content={"error": f"Unknown mode: {mode}. Use: diff, add, weekday, format"})


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-date-calc.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/calculate",
        "description": "Date calculations: diff, add, weekday, format",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3097, proxy_headers=True, forwarded_allow_ips="*")
