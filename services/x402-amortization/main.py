from __future__ import annotations
import os, time, math
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Amortization", version="1.0.0")


def _make_402(host: str, endpoint: str = "/calculate") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "Loan amortization schedule calculation",
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
            return _make_402(request.headers.get("host", "x402-amortization.suretat.com"))
    return await call_next(request)


class AmortizationRequest(BaseModel):
    principal: float
    rate_annual_pct: float
    duration_months: int
    currency: Optional[str] = "EUR"
    include_schedule: Optional[bool] = True


@app.get("/")
def root():
    return {"service": "x402 Amortization", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel", "docs": "/docs"}


@app.post("/calculate")
def calculate(req: AmortizationRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if req.principal <= 0:
        return JSONResponse(status_code=400, content={"error": "principal must be positive"})
    if req.rate_annual_pct < 0:
        return JSONResponse(status_code=400, content={"error": "rate cannot be negative"})
    if req.duration_months <= 0 or req.duration_months > 600:
        return JSONResponse(status_code=400, content={"error": "duration_months must be 1-600"})

    P = req.principal
    annual_rate = req.rate_annual_pct / 100.0
    n = req.duration_months
    currency = req.currency or "EUR"

    if annual_rate == 0:
        monthly_payment = P / n
        monthly_rate = 0.0
    else:
        monthly_rate = annual_rate / 12
        monthly_payment = P * (monthly_rate * (1 + monthly_rate) ** n) / ((1 + monthly_rate) ** n - 1)

    total_paid = monthly_payment * n
    total_interest = total_paid - P

    schedule = []
    if req.include_schedule:
        balance = P
        total_int_paid = 0.0
        total_principal_paid = 0.0
        for month in range(1, n + 1):
            interest_payment = balance * monthly_rate
            principal_payment = monthly_payment - interest_payment
            balance -= principal_payment
            if balance < 0:
                balance = 0.0
            total_int_paid += interest_payment
            total_principal_paid += principal_payment

            schedule.append({
                "month": month,
                "payment": round(monthly_payment, 2),
                "principal": round(principal_payment, 2),
                "interest": round(interest_payment, 2),
                "balance": round(max(0.0, balance), 2),
                "cumulative_interest": round(total_int_paid, 2),
            })

    return {
        "summary": {
            "principal": round(P, 2),
            "rate_annual_pct": req.rate_annual_pct,
            "duration_months": n,
            "duration_years": round(n / 12, 2),
            "monthly_payment": round(monthly_payment, 2),
            "total_paid": round(total_paid, 2),
            "total_interest": round(total_interest, 2),
            "interest_ratio_pct": round((total_interest / total_paid) * 100, 2) if total_paid > 0 else 0,
            "currency": currency,
        },
        "schedule": schedule if req.include_schedule else [],
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-amortization.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/calculate",
        "description": "Loan amortization schedule calculation",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3108, proxy_headers=True, forwarded_allow_ips="*")
