from __future__ import annotations
import os, re, time, math
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict

PORT = int(os.getenv("PORT", "3115"))
PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
HOST_DOMAIN = os.getenv("HOST_DOMAIN", "x402-doc-classifier.suretat.com")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Document Classifier", version="1.0.0")

# Document category keywords (FR + EN)
CATEGORIES: Dict[str, List[str]] = {
    "invoice": [
        "facture", "invoice", "montant", "amount", "total", "ttc", "ht", "tva", "vat",
        "paiement", "payment", "échéance", "due date", "numéro de facture", "invoice number",
        "client", "fournisseur", "supplier", "bon de commande", "purchase order",
        "siret", "siren", "iban", "bic", "règlement", "acompte", "solde",
    ],
    "cv": [
        "curriculum vitae", "cv", "résumé", "resume", "expérience professionnelle",
        "work experience", "formation", "education", "compétences", "skills",
        "diplôme", "degree", "poste", "position", "missions", "réalisations",
        "références", "references", "stage", "internship", "alternance",
    ],
    "contract": [
        "contrat", "contract", "accord", "agreement", "signataire", "signatory",
        "clause", "article", "parties", "obligations", "droits", "rights",
        "résiliation", "termination", "durée", "duration", "avenant", "amendment",
        "cdi", "cdd", "salarié", "employee", "employeur", "employer",
        "confidentialité", "confidentiality", "nda", "sous-traitance",
    ],
    "report": [
        "rapport", "report", "analyse", "analysis", "synthèse", "summary",
        "résultats", "results", "conclusions", "recommandations", "recommendations",
        "étude", "study", "bilan", "assessment", "indicateurs", "kpi",
        "performance", "tableau de bord", "dashboard", "statistiques", "statistics",
        "graphique", "chart", "tableau", "table", "figure",
    ],
    "email": [
        "de:", "from:", "à:", "to:", "objet:", "subject:", "cc:", "cci:", "bcc:",
        "cordialement", "regards", "bonjour", "hello", "madame", "monsieur",
        "veuillez", "please", "suite à", "following", "je vous contacte",
        "n'hésitez pas", "feel free", "bien à vous", "best regards",
        "pièce jointe", "attachment", "ci-joint",
    ],
    "legal": [
        "tribunal", "court", "jugement", "judgment", "arrêt", "ruling",
        "loi", "law", "article", "décret", "decree", "ordonnance", "ordinance",
        "juridique", "legal", "avocat", "lawyer", "jurisprudence",
        "plainte", "complaint", "procédure", "proceeding", "assignation",
        "propriété intellectuelle", "intellectual property", "brevet", "patent",
    ],
    "technical": [
        "api", "endpoint", "function", "class", "method", "variable", "code",
        "algorithm", "database", "server", "client", "protocol", "architecture",
        "dockerfile", "kubernetes", "deployment", "repository", "commit",
        "documentation technique", "technical documentation", "specification",
        "requirements", "readme", "changelog",
    ],
    "financial": [
        "bilan", "balance sheet", "compte de résultat", "income statement",
        "trésorerie", "cash flow", "actif", "assets", "passif", "liabilities",
        "capitaux propres", "equity", "chiffre d'affaires", "revenue", "ebitda",
        "résultat net", "net income", "bénéfice", "profit", "perte", "loss",
        "exercice", "fiscal year", "audit", "commissaire aux comptes",
    ],
    "medical": [
        "patient", "médecin", "doctor", "ordonnance", "prescription", "médicament",
        "medication", "diagnostic", "diagnosis", "traitement", "treatment",
        "symptômes", "symptoms", "examen", "examination", "résultats", "results",
        "laboratoire", "laboratory", "clinique", "clinic", "hôpital", "hospital",
        "antécédents", "medical history", "allergie", "allergy",
    ],
}

STOPWORDS_FR = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "est", "en", "au", "aux",
    "pour", "par", "sur", "dans", "avec", "que", "qui", "ce", "se", "sa", "son", "ses",
    "ou", "à", "il", "elle", "nous", "vous", "ils", "elles", "on", "y", "je", "tu",
    "me", "te", "lui", "leur", "leurs", "mon", "ma", "mes", "ton", "ta", "tes", "notre",
    "votre", "vos", "même", "plus", "bien", "très", "aussi", "car", "si", "mais", "donc",
}


def tokenize(text: str) -> List[str]:
    words = re.findall(r"\b\w+\b", text.lower())
    return [w for w in words if w not in STOPWORDS_FR and len(w) > 2]


def score_categories(text: str) -> Dict[str, float]:
    text_lower = text.lower()
    tokens = tokenize(text)
    token_set = set(tokens)
    total_tokens = max(len(tokens), 1)
    scores = {}
    for cat, keywords in CATEGORIES.items():
        matches = 0
        for kw in keywords:
            if " " in kw:
                if kw in text_lower:
                    matches += 2
            elif kw in token_set:
                matches += 1
        tf = matches / total_tokens
        idf = math.log(1 + len(CATEGORIES) / (1 + sum(
            1 for kws in CATEGORIES.values() if any(k in text_lower for k in kws)
        )))
        scores[cat] = round(tf * idf * 100, 3)
    return scores


def _make_402(host: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/classify",
            "description": "Classify document type (invoice, CV, contract, email, report, etc.)",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/classify" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", HOST_DOMAIN))
    return await call_next(request)


class ClassifyRequest(BaseModel):
    text: str
    top_k: Optional[int] = 3


@app.get("/")
def root():
    return {
        "service": "x402 Document Classifier",
        "description": "Classify document type: invoice, CV, contract, email, report, legal, technical, financial, medical.",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/call",
        "categories": list(CATEGORIES.keys()),
        "endpoint": "POST /classify",
        "docs": "/docs",
    }


@app.post("/classify")
def classify(req: ClassifyRequest):
    if not req.text or len(req.text.strip()) < 10:
        return JSONResponse(status_code=400, content={"error": "text too short"})

    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    text = req.text[:10000]
    top_k = max(1, min(req.top_k or 3, len(CATEGORIES)))

    scores = score_categories(text)
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top = sorted_scores[:top_k]
    best_cat, best_score = sorted_scores[0]
    total = sum(s for _, s in sorted_scores) or 1
    confidence = round(best_score / total, 4)

    return {
        "category": best_cat,
        "confidence": confidence,
        "scores": dict(top),
        "all_scores": scores,
        "word_count": len(text.split()),
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", HOST_DOMAIN)
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/classify",
        "description": "Classify document type (invoice, CV, contract, email, report, etc.)",
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
