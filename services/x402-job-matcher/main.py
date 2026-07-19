from __future__ import annotations
import os, re, time, math
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict

PORT = int(os.getenv("PORT", "3117"))
PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
HOST_DOMAIN = os.getenv("HOST_DOMAIN", "x402-job-matcher.suretat.com")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Job Matcher FR", version="1.0.0")

STOPWORDS = frozenset([
    "le","la","les","de","du","des","un","une","et","est","en","au","aux","pour","par",
    "sur","dans","avec","que","qui","ce","se","sa","son","ses","ou","à","il","elle",
    "nous","vous","ils","elles","on","y","je","tu","me","te","lui","leur","leurs",
    "mon","ma","mes","ton","ta","tes","notre","votre","vos","même","plus","bien",
    "très","aussi","car","si","mais","donc","or","ni","ne","pas","rien","tout",
    "être","avoir","faire","pouvoir","vouloir","devoir","aller","venir","voir",
    "the","a","an","and","or","but","in","on","at","to","for","of","with","is",
    "are","was","were","be","been","being","have","has","had","do","does","did",
    "will","would","could","should","may","might","shall","can","not","this","that",
])

# Skill importance weights
SKILL_WEIGHTS = {
    # Languages
    "python": 3, "javascript": 3, "typescript": 3, "java": 3, "c++": 3, "c#": 3,
    "go": 3, "rust": 3, "php": 2, "ruby": 2, "swift": 2, "kotlin": 2, "scala": 2,
    # Frameworks
    "react": 2.5, "vue": 2.5, "angular": 2.5, "django": 2.5, "fastapi": 2.5,
    "flask": 2, "spring": 2.5, "node": 2.5, "express": 2, "nextjs": 2.5,
    # Infra
    "docker": 2.5, "kubernetes": 3, "aws": 3, "azure": 2.5, "gcp": 2.5,
    "terraform": 2.5, "ansible": 2, "ci/cd": 2, "git": 2, "linux": 2,
    # DB
    "sql": 2.5, "postgresql": 2.5, "mysql": 2, "mongodb": 2, "redis": 2,
    "elasticsearch": 2.5, "kafka": 2.5,
    # ML/AI
    "machine learning": 3, "deep learning": 3, "nlp": 3, "llm": 3,
    "pytorch": 3, "tensorflow": 3, "scikit-learn": 2.5, "pandas": 2, "numpy": 2,
    # Tools
    "graphql": 2, "rest": 2, "api": 1.5, "microservices": 2.5, "agile": 1.5,
    "scrum": 1.5, "devops": 2.5, "sre": 2.5,
}

# Experience keywords
YEARS_RE = re.compile(
    r"(\d+)\s*(?:\+\s*)?(?:ans?|années?|years?)\s*(?:d['']expérience|d'exp|experience|of experience)",
    re.I
)
XP_LEVEL_KEYWORDS = {
    "junior": 1, "débutant": 1, "entry level": 1, "entry-level": 1,
    "confirmé": 3, "experienced": 3, "mid-level": 3, "intermédiaire": 3,
    "senior": 5, "lead": 7, "principal": 7, "expert": 7, "architecte": 8,
    "manager": 5, "directeur": 8, "vp": 10, "cto": 10,
}

# Contract types
CONTRACT_RE = re.compile(r"\b(cdi|cdd|alternance|stage|freelance|consultant|intérim|full.?time|part.?time|remote|télétravail)\b", re.I)


def tokenize(text: str) -> set:
    tokens = re.findall(r"\b\w+\b", text.lower())
    return {t for t in tokens if t not in STOPWORDS and len(t) > 2}


def extract_skills(text: str) -> Dict[str, float]:
    text_lower = text.lower()
    found = {}
    for skill, weight in SKILL_WEIGHTS.items():
        if skill in text_lower:
            found[skill] = weight
    return found


def extract_experience_years(text: str) -> Optional[int]:
    matches = YEARS_RE.findall(text)
    if matches:
        return max(int(m) for m in matches)
    text_lower = text.lower()
    for kw, years in XP_LEVEL_KEYWORDS.items():
        if kw in text_lower:
            return years
    return None


def tfidf_similarity(text1: str, text2: str) -> float:
    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1 & tokens2
    # Jaccard + skill-weighted cosine hybrid
    jaccard = len(intersection) / len(tokens1 | tokens2)
    # Skill-weighted bonus
    skill_bonus = 0.0
    text1_lower = text1.lower()
    text2_lower = text2.lower()
    matched_skills = []
    for skill, weight in SKILL_WEIGHTS.items():
        if skill in text1_lower and skill in text2_lower:
            skill_bonus += weight * 0.02
            matched_skills.append(skill)
    score = min(1.0, jaccard * 0.6 + skill_bonus * 0.4)
    return round(score, 4), matched_skills


def _make_402(host: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/match",
            "description": "Match a job description with a candidate profile (FR/EN)",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/match" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", HOST_DOMAIN))
    return await call_next(request)


class MatchRequest(BaseModel):
    job_description: str
    candidate_profile: str


@app.get("/")
def root():
    return {
        "service": "x402 Job Matcher FR",
        "description": "Match a job description against a candidate profile. Returns match score, matched skills, and experience fit.",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/call",
        "endpoint": "POST /match",
        "docs": "/docs",
    }


@app.post("/match")
def match(req: MatchRequest):
    if not req.job_description or not req.candidate_profile:
        return JSONResponse(status_code=400, content={"error": "job_description and candidate_profile required"})
    if len(req.job_description) < 20 or len(req.candidate_profile) < 20:
        return JSONResponse(status_code=400, content={"error": "texts too short"})

    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    job = req.job_description[:5000]
    profile = req.candidate_profile[:5000]

    similarity_result = tfidf_similarity(job, profile)
    if isinstance(similarity_result, tuple):
        similarity, matched_skills = similarity_result
    else:
        similarity, matched_skills = similarity_result, []

    job_skills = extract_skills(job)
    profile_skills = extract_skills(profile)
    missing_skills = sorted(set(job_skills) - set(profile_skills))
    extra_skills = sorted(set(profile_skills) - set(job_skills))

    job_xp = extract_experience_years(job)
    profile_xp = extract_experience_years(profile)
    xp_fit = None
    if job_xp and profile_xp:
        if profile_xp >= job_xp:
            xp_fit = "match"
        elif profile_xp >= job_xp * 0.7:
            xp_fit = "partial"
        else:
            xp_fit = "insufficient"

    job_contracts = [m.group(0).lower() for m in CONTRACT_RE.finditer(job)]

    # Overall score (0-100)
    skill_match_pct = len(matched_skills) / max(len(job_skills), 1) if job_skills else 0
    score = round((similarity * 0.4 + skill_match_pct * 0.6) * 100, 1)

    return {
        "score": score,
        "score_label": "excellent" if score >= 70 else "good" if score >= 50 else "partial" if score >= 30 else "low",
        "text_similarity": similarity,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills[:10],
        "extra_skills": extra_skills[:10],
        "experience_required": job_xp,
        "experience_candidate": profile_xp,
        "experience_fit": xp_fit,
        "contract_types": job_contracts,
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", HOST_DOMAIN)
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/match",
        "description": "Match a job description with a candidate profile (FR/EN)",
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
