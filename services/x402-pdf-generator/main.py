"""
x402 PDF Generator FR — génération de PDF professionnels depuis HTML/JSON
Moteur: WeasyPrint (pur Python, CSS3, fonts)
Templates: facture, devis, rapport simple
Prix: 0.005 USDC/appel
"""
from __future__ import annotations
import os, base64, html
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
import weasyprint

load_dotenv()

WALLET       = os.getenv("WALLET_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "5000")   # 0.005 USDC
FACILITATOR  = os.getenv("FACILITATOR_URL", "https://api.cdp.coinbase.com/platform/v2/x402")
USDC_BASE    = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

payments_total = 0
payments_log: list = []

PAYMENT_REQUIREMENTS = {
    "scheme": "exact",
    "network": "base",
    "maxAmountRequired": PRICE_ATOMIC,
    "resource": "https://x402-pdf.suretat.com/generate",
    "description": "Génération PDF professionnel depuis HTML/JSON — factures, devis, rapports",
    "mimeType": "application/pdf",
    "payTo": WALLET,
    "maxTimeoutSeconds": 300,
    "asset": USDC_BASE,
    "extra": {
        "name": "USD Coin",
        "version": "2",
        "bazaar": {
            "bodyType": "json",
            "input": {
                "template": "facture",
                "data": {
                    "numero": "2024-001",
                    "date": "2024-01-15",
                    "emetteur": {"nom": "Ma Société", "siret": "123456789 00001"},
                    "client": {"nom": "Client SAS"},
                    "lignes": [{"desc": "Prestation", "qty": 1, "pu": 100}],
                    "tva": 20,
                }
            },
            "inputSchema": {
                "properties": {
                    "template": {"type": "string", "enum": ["facture", "devis", "rapport"], "description": "Type de document"},
                    "data": {"type": "object", "description": "Données du document"},
                    "html": {"type": "string", "description": "HTML brut (alternative aux templates)"},
                },
            },
            "output": {"example": {"pdf_base64": "JVBERi0xLjQK...", "pages": 1, "size_bytes": 45678}},
        },
    },
}


def e(s) -> str:
    return html.escape(str(s)) if s else ""


def render_facture(data: dict) -> str:
    em = data.get("emetteur", {})
    cl = data.get("client", {})
    lignes = data.get("lignes", [])
    tva_pct = float(data.get("tva", 20))
    
    rows = ""
    subtotal = 0.0
    for lg in lignes:
        total = float(lg.get("qty", 1)) * float(lg.get("pu", 0))
        subtotal += total
        rows += f"""
        <tr>
          <td>{e(lg.get('desc',''))}</td>
          <td class="right">{e(lg.get('qty',1))}</td>
          <td class="right">{float(lg.get('pu',0)):.2f} €</td>
          <td class="right">{total:.2f} €</td>
        </tr>"""
    
    tva_amt = subtotal * tva_pct / 100
    total_ttc = subtotal + tva_amt

    return f"""<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="UTF-8">
<style>
  body {{ font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 12px; color: #333; margin: 0; padding: 40px; }}
  h1 {{ color: #2c3e50; font-size: 24px; margin-bottom: 5px; }}
  .header {{ display: flex; justify-content: space-between; margin-bottom: 30px; }}
  .meta {{ text-align: right; }}
  .parties {{ display: flex; gap: 40px; margin: 20px 0 30px; }}
  .partie {{ flex: 1; padding: 15px; background: #f8f9fa; border-radius: 4px; }}
  .partie h3 {{ margin: 0 0 8px; color: #2c3e50; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
  th {{ background: #2c3e50; color: white; padding: 10px; text-align: left; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #eee; }}
  .right {{ text-align: right; }}
  .totaux {{ float: right; width: 280px; margin-top: 10px; }}
  .totaux table {{ margin: 0; }}
  .totaux td {{ border: none; padding: 5px 10px; }}
  .total-ttc {{ font-weight: bold; font-size: 14px; background: #2c3e50; color: white; }}
  .footer {{ clear: both; margin-top: 60px; font-size: 10px; color: #999; text-align: center; border-top: 1px solid #eee; padding-top: 15px; }}
</style>
</head><body>
<div class="header">
  <div>
    <h1>{'DEVIS' if data.get('type')=='devis' else 'FACTURE'}</h1>
    <div>N° {e(data.get('numero',''))}</div>
  </div>
  <div class="meta">
    <div>Date: {e(data.get('date',''))}</div>
    {f"<div>Échéance: {e(data.get('echeance',''))}</div>" if data.get('echeance') else ''}
  </div>
</div>

<div class="parties">
  <div class="partie">
    <h3>Émetteur</h3>
    <div><strong>{e(em.get('nom',''))}</strong></div>
    {f"<div>{e(em.get('adresse',''))}</div>" if em.get('adresse') else ''}
    {f"<div>SIRET: {e(em.get('siret',''))}</div>" if em.get('siret') else ''}
    {f"<div>TVA: {e(em.get('tva_intra',''))}</div>" if em.get('tva_intra') else ''}
  </div>
  <div class="partie">
    <h3>Client</h3>
    <div><strong>{e(cl.get('nom',''))}</strong></div>
    {f"<div>{e(cl.get('adresse',''))}</div>" if cl.get('adresse') else ''}
    {f"<div>SIRET: {e(cl.get('siret',''))}</div>" if cl.get('siret') else ''}
  </div>
</div>

<table>
  <thead><tr><th>Description</th><th class="right">Qté</th><th class="right">P.U. HT</th><th class="right">Total HT</th></tr></thead>
  <tbody>{rows}</tbody>
</table>

<div class="totaux">
  <table>
    <tr><td>Sous-total HT</td><td class="right">{subtotal:.2f} €</td></tr>
    <tr><td>TVA {tva_pct:.0f}%</td><td class="right">{tva_amt:.2f} €</td></tr>
    <tr class="total-ttc"><td>Total TTC</td><td class="right">{total_ttc:.2f} €</td></tr>
  </table>
</div>

<div class="footer">
  {e(em.get('nom',''))} {f"— SIRET {e(em.get('siret',''))}" if em.get('siret') else ''}
  {f" — {e(em.get('email',''))}" if em.get('email') else ''}
</div>
</body></html>"""


async def cdp_call(endpoint: str, payment_header: str) -> bool:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{FACILITATOR}/{endpoint}",
                json={"x402Version": 1, "paymentHeader": payment_header, "paymentRequirements": [PAYMENT_REQUIREMENTS]},
            )
            if endpoint == "verify":
                return resp.json().get("isValid", False)
            return resp.status_code == 200
        except Exception:
            return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[x402-pdf] Wallet: {WALLET} | WeasyPrint ready")
    yield


app = FastAPI(title="x402 PDF Generator FR", version="1.0.0", lifespan=lifespan)


class PDFRequest(BaseModel):
    template: Optional[str] = None   # facture | devis | rapport
    data: Optional[dict] = None
    html: Optional[str] = None       # HTML brut (alternative)
    return_base64: bool = True        # True = JSON avec base64, False = binaire PDF


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if not request.url.path.startswith("/generate"):
        return await call_next(request)
    payment_header = request.headers.get("X-PAYMENT")
    if not payment_header:
        return JSONResponse(
            status_code=402,
            content={"x402Version": 1, "accepts": [PAYMENT_REQUIREMENTS], "error": "Payment required"},
                    headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
        )
    if not await cdp_call("verify", payment_header):
        return JSONResponse(status_code=402, content={"x402Version": 1, "error": "Paiement invalide ou expiré"}, headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"})
    response = await call_next(request)
    await cdp_call("settle", payment_header)
    global payments_total, payments_log
    payments_total += 1
    payments_log.append({"n": payments_total, "at": datetime.now(timezone.utc).isoformat()})
    if len(payments_log) > 100:
        payments_log = payments_log[-100:]
    print(f"[x402-pdf] PAIEMENT #{payments_total}")
    return response


@app.get("/")
async def root():
    return {
        "service": "x402 PDF Generator FR",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.005 USDC/PDF",
        "endpoint": "POST /generate",
        "templates": ["facture", "devis"],
        "engine": "WeasyPrint (CSS3)",
        "docs": "/docs",
        "tagline": "Convert HTML to PDF — headers, footers, custom page size",
        "curl_example": "curl https://x402-pdf-generator.suretat.com/generate -H 'Content-Type: application/json' -d '{\"html\": \"<h1>Invoice</h1><p>Amount: 100 EUR</p>\", \"format\": \"A4\"}'",
        "try_it": "https://x402-pdf-generator.suretat.com/docs",
    }


@app.post("/generate")
async def generate_pdf(payload: PDFRequest):
    if payload.html:
        html_content = payload.html
    elif payload.template in ("facture", "devis"):
        data = payload.data or {}
        if payload.template == "devis":
            data["type"] = "devis"
        html_content = render_facture(data)
    else:
        return JSONResponse(
            status_code=400,
            content={"error": "Fournir 'html' ou 'template' (facture|devis) avec 'data'"},
        )

    try:
        pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()
    except Exception as ex:
        return JSONResponse(status_code=500, content={"error": f"WeasyPrint error: {str(ex)[:200]}"})

    if payload.return_base64:
        return {
            "pdf_base64": base64.b64encode(pdf_bytes).decode(),
            "size_bytes": len(pdf_bytes),
        }
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=document.pdf"})


@app.get("/stats")
async def stats():
    return {"service": "x402-pdf-generator", "payments_total": payments_total, "last_payments": payments_log[-10:]}

@app.get("/.well-known/x402.json")
async def x402_well_known():
    return {"x402Version": 1, "accepts": [PAYMENT_REQUIREMENTS]}

@app.get("/.well-known/x402")
async def x402_well_known_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/.well-known/x402.json")

