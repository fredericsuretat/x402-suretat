from __future__ import annotations
import os, re, time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List

PORT = int(os.getenv("PORT", "3114"))
PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
HOST_DOMAIN = os.getenv("HOST_DOMAIN", "x402-cv-parser.suretat.com")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 CV Parser FR", version="1.0.0")

# Skills keyword database
TECH_SKILLS = {
    "python", "javascript", "typescript", "java", "c#", "c++", "go", "rust", "php", "ruby",
    "swift", "kotlin", "scala", "r", "matlab", "sql", "nosql", "html", "css",
    "react", "vue", "angular", "nextjs", "nuxt", "svelte", "node", "express", "fastapi",
    "django", "flask", "spring", "laravel", "rails", "docker", "kubernetes", "aws", "azure",
    "gcp", "terraform", "ansible", "ci/cd", "git", "linux", "bash", "postgresql", "mysql",
    "mongodb", "redis", "elasticsearch", "kafka", "rabbitmq", "graphql", "rest", "api",
    "machine learning", "deep learning", "nlp", "llm", "pytorch", "tensorflow", "scikit-learn",
    "pandas", "numpy", "spark", "hadoop", "airflow", "dbt", "power bi", "tableau", "excel",
}

SOFT_SKILLS_FR = {
    "autonome", "autonomie", "rigoureux", "rigueur", "organisation", "organisé",
    "communication", "communicant", "travail en équipe", "équipe", "leadership",
    "management", "gestion", "analyse", "analytique", "créativité", "créatif",
    "proactif", "adaptable", "adaptabilité", "curiosité", "curieux", "force de proposition",
    "problem solving", "résolution de problèmes", "prise de décision",
}

DEGREES_FR = {
    "bac": 1, "bac+2": 2, "bts": 2, "dut": 2, "iut": 2, "bac+3": 3, "licence": 3,
    "bac+4": 4, "master": 5, "bac+5": 5, "ingénieur": 5, "mba": 5,
    "doctorat": 8, "phd": 8, "bts": 2,
}

EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
PHONE_RE = re.compile(r"(?:\+33|0)[1-9](?:[\s.\-]?\d{2}){4}")
LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w\-]+", re.I)
GITHUB_RE = re.compile(r"github\.com/[\w\-]+", re.I)

YEAR_RANGE_RE = re.compile(r"\b(20\d{2}|19\d{2})\s*[-–]\s*(20\d{2}|19\d{2}|présent|present|aujourd'hui|actuel)\b", re.I)
SINGLE_YEAR_RE = re.compile(r"\b(20\d{2}|19[89]\d)\b")

SECTION_HEADERS_FR = re.compile(
    r"^(expérience|experiences?|parcours|emploi|poste|missions?|"
    r"formation|études?|diplômes?|éducation|"
    r"compétences?|skills?|technologies?|outils?|"
    r"langues?|certifications?|projets?|réalisations?|"
    r"loisirs?|centres? d'intérêts?|hobbies?)\s*:?\s*$",
    re.I | re.M,
)

def extract_contact(text: str) -> dict:
    emails = EMAIL_RE.findall(text)
    phones = PHONE_RE.findall(text)
    linkedin = LINKEDIN_RE.findall(text)
    github = GITHUB_RE.findall(text)
    # Try to extract name from first non-empty line
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    name_candidate = lines[0] if lines else ""
    # Simple heuristic: name is typically 2-3 capitalized words on first line
    name = None
    if re.match(r"^[A-ZÀÂÄÉÈÊËÏÎÔÙÛÜ][a-zàâäéèêëïîôùûü]+(?:\s+[A-ZÀÂÄÉÈÊËÏÎÔÙÛÜ][a-zàâäéèêëïîôùûü]+){1,2}$", name_candidate):
        name = name_candidate
    return {
        "name": name,
        "email": emails[0] if emails else None,
        "phone": phones[0] if phones else None,
        "linkedin": linkedin[0] if linkedin else None,
        "github": github[0] if github else None,
    }

def extract_skills(text: str) -> dict:
    text_lower = text.lower()
    found_tech = sorted([s for s in TECH_SKILLS if s in text_lower])
    found_soft = sorted([s for s in SOFT_SKILLS_FR if s in text_lower])
    return {"technical": found_tech, "soft": found_soft}

def extract_education(text: str) -> dict:
    text_lower = text.lower()
    max_level = 0
    highest_degree = None
    for deg, level in DEGREES_FR.items():
        if deg in text_lower and level > max_level:
            max_level = level
            highest_degree = deg
    years = YEAR_RANGE_RE.findall(text)
    return {
        "highest_degree": highest_degree,
        "level_years": max_level,
        "periods_found": [f"{y[0]}-{y[1]}" for y in years[:5]],
    }

def extract_experience(text: str) -> dict:
    years_mentioned = [int(y) for y in SINGLE_YEAR_RE.findall(text)]
    if years_mentioned:
        oldest = min(years_mentioned)
        estimated_xp = max(0, 2026 - oldest)
    else:
        estimated_xp = None
    ranges = YEAR_RANGE_RE.findall(text)
    total_months = 0
    for start_y, end_y in ranges:
        try:
            s = int(start_y)
            e = 2026 if end_y.lower() in ("présent", "present", "aujourd'hui", "actuel") else int(end_y)
            total_months += max(0, (e - s) * 12)
        except ValueError:
            pass
    return {
        "estimated_years": estimated_xp,
        "total_months_calculated": total_months if total_months else None,
        "date_ranges": [f"{y[0]}-{y[1]}" for y in ranges[:10]],
    }

def extract_languages(text: str) -> List[str]:
    lang_keywords = {
        "français": "Français", "french": "Français",
        "anglais": "Anglais", "english": "Anglais",
        "espagnol": "Espagnol", "spanish": "Espagnol",
        "allemand": "Allemand", "german": "Allemand",
        "italien": "Italien", "italian": "Italien",
        "portugais": "Portugais", "portuguese": "Portugais",
        "chinois": "Chinois", "chinese": "Chinois", "mandarin": "Chinois",
        "arabe": "Arabe", "arabic": "Arabe",
        "japonais": "Japonais", "japanese": "Japonais",
    }
    text_lower = text.lower()
    found = {}
    for kw, lang in lang_keywords.items():
        if kw in text_lower:
            found[lang] = True
    return sorted(found.keys())


def _make_402(host: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/parse",
            "description": "Parse a CV/resume text into structured JSON (FR/EN)",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/parse" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", HOST_DOMAIN))
    return await call_next(request)


class ParseRequest(BaseModel):
    text: str
    lang: Optional[str] = "auto"


@app.get("/")
def root():
    return {
        "service": "x402 CV Parser FR",
        "description": "Parse CV/resume text into structured JSON. Extracts contact, skills, education, experience, languages.",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/call",
        "endpoint": "POST /parse",
        "docs": "/docs",
    }


@app.post("/parse")
def parse_cv(req: ParseRequest):
    if not req.text or len(req.text.strip()) < 20:
        return JSONResponse(status_code=400, content={"error": "text too short"})

    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    text = req.text[:8000]  # cap at 8KB
    return {
        "contact": extract_contact(text),
        "skills": extract_skills(text),
        "education": extract_education(text),
        "experience": extract_experience(text),
        "languages": extract_languages(text),
        "char_count": len(text),
        "word_count": len(text.split()),
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", HOST_DOMAIN)
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/parse",
        "description": "Parse a CV/resume text into structured JSON (FR/EN)",
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
