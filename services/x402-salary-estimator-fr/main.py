from __future__ import annotations
import os, re, time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List

PORT = int(os.getenv("PORT", "3118"))
PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
HOST_DOMAIN = os.getenv("HOST_DOMAIN", "x402-salary-estimator-fr.suretat.com")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Salary Estimator FR", version="1.0.0")

# French salary database (annual gross, EUR, 2024-2025)
# Source: APEC, Glassdoor FR, INSEE, Hellowork
SALARY_DB = {
    # Tech
    "développeur": {"junior": 32000, "mid": 42000, "senior": 55000, "lead": 70000},
    "developpeur": {"junior": 32000, "mid": 42000, "senior": 55000, "lead": 70000},
    "developer": {"junior": 32000, "mid": 42000, "senior": 55000, "lead": 70000},
    "dev": {"junior": 32000, "mid": 42000, "senior": 55000, "lead": 70000},
    "ingénieur logiciel": {"junior": 35000, "mid": 48000, "senior": 62000, "lead": 78000},
    "software engineer": {"junior": 38000, "mid": 52000, "senior": 68000, "lead": 85000},
    "devops": {"junior": 38000, "mid": 52000, "senior": 65000, "lead": 80000},
    "sre": {"junior": 40000, "mid": 55000, "senior": 70000, "lead": 85000},
    "data scientist": {"junior": 38000, "mid": 52000, "senior": 68000, "lead": 82000},
    "data engineer": {"junior": 38000, "mid": 52000, "senior": 65000, "lead": 78000},
    "data analyst": {"junior": 32000, "mid": 42000, "senior": 55000, "lead": 68000},
    "machine learning": {"junior": 40000, "mid": 55000, "senior": 72000, "lead": 90000},
    "ml engineer": {"junior": 40000, "mid": 55000, "senior": 72000, "lead": 90000},
    "ia": {"junior": 40000, "mid": 55000, "senior": 72000, "lead": 90000},
    "ai engineer": {"junior": 42000, "mid": 58000, "senior": 75000, "lead": 95000},
    "architecte": {"junior": 45000, "mid": 62000, "senior": 78000, "lead": 95000},
    "architect": {"junior": 45000, "mid": 62000, "senior": 78000, "lead": 95000},
    "frontend": {"junior": 32000, "mid": 42000, "senior": 55000, "lead": 68000},
    "backend": {"junior": 34000, "mid": 45000, "senior": 58000, "lead": 72000},
    "fullstack": {"junior": 35000, "mid": 46000, "senior": 60000, "lead": 75000},
    "full stack": {"junior": 35000, "mid": 46000, "senior": 60000, "lead": 75000},
    "mobile": {"junior": 33000, "mid": 44000, "senior": 57000, "lead": 70000},
    "ios": {"junior": 35000, "mid": 48000, "senior": 62000, "lead": 75000},
    "android": {"junior": 35000, "mid": 48000, "senior": 62000, "lead": 75000},
    "cloud": {"junior": 38000, "mid": 52000, "senior": 68000, "lead": 82000},
    "cybersécurité": {"junior": 38000, "mid": 52000, "senior": 68000, "lead": 82000},
    "cybersecurity": {"junior": 38000, "mid": 52000, "senior": 68000, "lead": 82000},
    "secops": {"junior": 38000, "mid": 52000, "senior": 68000, "lead": 82000},
    "product manager": {"junior": 38000, "mid": 52000, "senior": 68000, "lead": 85000},
    "product owner": {"junior": 35000, "mid": 48000, "senior": 62000, "lead": 78000},
    "scrum master": {"junior": 35000, "mid": 48000, "senior": 62000, "lead": 75000},
    "chef de projet": {"junior": 32000, "mid": 45000, "senior": 58000, "lead": 72000},
    "project manager": {"junior": 32000, "mid": 45000, "senior": 58000, "lead": 72000},
    "ux designer": {"junior": 30000, "mid": 40000, "senior": 52000, "lead": 65000},
    "ui designer": {"junior": 28000, "mid": 37000, "senior": 48000, "lead": 60000},
    "designer": {"junior": 28000, "mid": 37000, "senior": 48000, "lead": 60000},
    # Management
    "directeur technique": {"junior": 65000, "mid": 85000, "senior": 110000, "lead": 140000},
    "cto": {"junior": 70000, "mid": 95000, "senior": 125000, "lead": 160000},
    "ceo": {"junior": 60000, "mid": 90000, "senior": 130000, "lead": 200000},
    "dsi": {"junior": 65000, "mid": 85000, "senior": 110000, "lead": 140000},
    "manager": {"junior": 38000, "mid": 52000, "senior": 68000, "lead": 85000},
    "team lead": {"junior": 45000, "mid": 58000, "senior": 72000, "lead": 85000},
    # Finance
    "comptable": {"junior": 28000, "mid": 36000, "senior": 48000, "lead": 62000},
    "contrôleur de gestion": {"junior": 35000, "mid": 48000, "senior": 62000, "lead": 78000},
    "analyste financier": {"junior": 38000, "mid": 52000, "senior": 68000, "lead": 85000},
    # HR
    "rh": {"junior": 28000, "mid": 36000, "senior": 48000, "lead": 62000},
    "recruteur": {"junior": 28000, "mid": 38000, "senior": 50000, "lead": 65000},
    # Marketing
    "marketing": {"junior": 28000, "mid": 36000, "senior": 48000, "lead": 65000},
    "growth hacker": {"junior": 32000, "mid": 42000, "senior": 55000, "lead": 70000},
    "seo": {"junior": 28000, "mid": 36000, "senior": 48000, "lead": 60000},
    # Sales
    "commercial": {"junior": 30000, "mid": 42000, "senior": 58000, "lead": 75000},
    "business developer": {"junior": 32000, "mid": 45000, "senior": 60000, "lead": 80000},
    "account manager": {"junior": 32000, "mid": 45000, "senior": 60000, "lead": 80000},
}

# Region multipliers (Paris = 1.0 baseline)
REGION_MULTIPLIERS = {
    "paris": 1.0, "ile-de-france": 1.0, "idf": 1.0,
    "lyon": 0.87, "marseille": 0.82, "bordeaux": 0.85, "toulouse": 0.85,
    "lille": 0.83, "nantes": 0.84, "strasbourg": 0.85, "nice": 0.86,
    "rennes": 0.82, "montpellier": 0.82, "grenoble": 0.88, "rouen": 0.83,
    "remote": 0.92, "télétravail": 0.92, "full remote": 0.92, "distanciel": 0.92,
}

# Experience to level mapping
def years_to_level(years: int) -> str:
    if years <= 2:
        return "junior"
    if years <= 5:
        return "mid"
    if years <= 10:
        return "senior"
    return "lead"

YEARS_RE = re.compile(r"(\d+)\s*(?:ans?|années?|years?)", re.I)


def find_job_category(title: str) -> Optional[tuple]:
    title_lower = title.lower()
    # Try exact match first (longest match wins)
    best = None
    best_len = 0
    for key, data in SALARY_DB.items():
        if key in title_lower and len(key) > best_len:
            best = (key, data)
            best_len = len(key)
    return best


def find_region_multiplier(location: str) -> tuple:
    if not location:
        return 1.0, "paris"
    loc_lower = location.lower()
    for region, mult in REGION_MULTIPLIERS.items():
        if region in loc_lower:
            return mult, region
    return 0.85, "province"  # Default province


def _make_402(host: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/estimate",
            "description": "Estimate French salary by job title, experience and region",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/estimate" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", HOST_DOMAIN))
    return await call_next(request)


class EstimateRequest(BaseModel):
    job_title: str
    experience_years: Optional[int] = None
    location: Optional[str] = "Paris"
    contract_type: Optional[str] = "CDI"


@app.get("/")
def root():
    return {
        "service": "x402 Salary Estimator FR",
        "description": "Estimate French gross annual salary by job title, experience and region. Data: APEC/Glassdoor/INSEE 2024-2025.",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/call",
        "endpoint": "POST /estimate",
        "supported_jobs": len(SALARY_DB),
        "supported_regions": len(REGION_MULTIPLIERS),
        "docs": "/docs",
    }


@app.post("/estimate")
def estimate(req: EstimateRequest):
    if not req.job_title or len(req.job_title.strip()) < 2:
        return JSONResponse(status_code=400, content={"error": "job_title required"})

    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    category = find_job_category(req.job_title)
    if not category:
        return JSONResponse(
            status_code=404,
            content={
                "error": "job title not found in database",
                "hint": "Try more generic titles like 'développeur', 'data scientist', 'devops', 'manager'...",
                "available_jobs": sorted(SALARY_DB.keys())[:20],
            }
        )

    matched_key, salary_data = category
    years = req.experience_years
    if years is None:
        years = 3  # default mid-level

    level = years_to_level(years)
    base_salary = salary_data[level]
    region_mult, matched_region = find_region_multiplier(req.location or "Paris")

    adjusted = round(base_salary * region_mult)

    # Paris base salaries for reference
    paris_salaries = {lvl: sal for lvl, sal in salary_data.items()}

    # Freelance premium (+30-40%)
    if req.contract_type and req.contract_type.lower() in ("freelance", "consultant"):
        daily_rate_min = round(adjusted / 220 * 1.3 / 8 * 8)
        daily_rate_max = round(adjusted / 220 * 1.5 / 8 * 8)
        monthly_gross = round(adjusted / 12)
    else:
        daily_rate_min = None
        daily_rate_max = None
        monthly_gross = round(adjusted / 12)

    return {
        "job_matched": matched_key,
        "experience_years": years,
        "level": level,
        "location": req.location,
        "region_matched": matched_region,
        "region_coefficient": region_mult,
        "contract_type": req.contract_type,
        "salary": {
            "annual_gross": adjusted,
            "monthly_gross": monthly_gross,
            "annual_net_estimate": round(adjusted * 0.77),
            "monthly_net_estimate": round(adjusted * 0.77 / 12),
        },
        "salary_range": {
            "min": round(adjusted * 0.9),
            "median": adjusted,
            "max": round(adjusted * 1.15),
        },
        "paris_reference": {
            lvl: {"annual_gross": sal, "annual_net": round(sal * 0.77)}
            for lvl, sal in paris_salaries.items()
        },
        "daily_rate_freelance": {
            "min": daily_rate_min,
            "max": daily_rate_max,
        } if daily_rate_min else None,
        "source": "APEC / Glassdoor FR / INSEE 2024-2025 (indicatif)",
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", HOST_DOMAIN)
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/estimate",
        "description": "Estimate French salary by job title, experience and region",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")
