from __future__ import annotations
import base64
import io
import os
import time
from datetime import datetime
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fpdf import FPDF
from pydantic import BaseModel, Field

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "5000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Invoice Generator", version="1.0.0")


class Company(BaseModel):
    name: str
    address: str
    siret: Optional[str] = None
    tva_number: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class Client(BaseModel):
    name: str
    address: str
    email: Optional[str] = None
    siret: Optional[str] = None
    tva_number: Optional[str] = None


class InvoiceMeta(BaseModel):
    number: str
    date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    due_date: Optional[str] = None
    currency: str = "EUR"


class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    tva_rate: float = 20.0
    unit: str = "u."


class InvoiceRequest(BaseModel):
    company: Company
    client: Client
    invoice: InvoiceMeta
    items: List[LineItem]
    notes: Optional[str] = None
    payment_info: Optional[str] = None


def _build_pdf(req: InvoiceRequest) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # En-tête entreprise
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 10, req.company.name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(0, 5, req.company.address)
    for label, val in [
        ("SIRET", req.company.siret),
        ("N° TVA", req.company.tva_number),
        ("Email", req.company.email),
        ("Tél", req.company.phone),
    ]:
        if val:
            pdf.cell(0, 5, f"{label} : {val}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    # Titre facture
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 9, f"FACTURE N° {req.invoice.number}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Date : {req.invoice.date}", new_x="LMARGIN", new_y="NEXT")
    if req.invoice.due_date:
        pdf.cell(0, 6, f"Échéance : {req.invoice.due_date}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Bloc client
    pdf.set_fill_color(245, 245, 245)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Facturé à :", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, req.client.name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, req.client.address)
    for label, val in [("Email", req.client.email), ("SIRET", req.client.siret), ("N° TVA", req.client.tva_number)]:
        if val:
            pdf.cell(0, 5, f"{label} : {val}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(7)

    # En-tête tableau
    col_w = [88, 20, 32, 22, 28]
    headers = ["Description", "Qté", "P.U. HT", "TVA %", "Total HT"]
    pdf.set_fill_color(40, 40, 40)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 8, h, border=1, fill=True, align="C")
    pdf.ln()

    # Lignes
    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Helvetica", "", 9)
    subtotal_ht = 0.0
    tva_by_rate: dict[float, float] = {}
    for item in req.items:
        ht = round(item.quantity * item.unit_price, 2)
        subtotal_ht += ht
        tva_by_rate[item.tva_rate] = tva_by_rate.get(item.tva_rate, 0.0) + ht * item.tva_rate / 100
        pdf.cell(col_w[0], 7, item.description[:55], border=1)
        pdf.cell(col_w[1], 7, f"{item.quantity:g} {item.unit}", border=1, align="C")
        pdf.cell(col_w[2], 7, f"{item.unit_price:.2f} {req.invoice.currency}", border=1, align="R")
        pdf.cell(col_w[3], 7, f"{item.tva_rate:.1f}%", border=1, align="C")
        pdf.cell(col_w[4], 7, f"{ht:.2f} {req.invoice.currency}", border=1, align="R")
        pdf.ln()

    pdf.ln(5)

    # Totaux (alignés à droite)
    total_tva = sum(tva_by_rate.values())
    total_ttc = subtotal_ht + total_tva
    cur = req.invoice.currency
    x0 = 125

    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(x0)
    pdf.cell(45, 7, "Total HT :", align="R")
    pdf.cell(30, 7, f"{subtotal_ht:.2f} {cur}", align="R", new_x="LMARGIN", new_y="NEXT")
    for rate, tva_amt in sorted(tva_by_rate.items()):
        pdf.set_x(x0)
        pdf.cell(45, 7, f"TVA {rate:.1f}% :", align="R")
        pdf.cell(30, 7, f"{tva_amt:.2f} {cur}", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_fill_color(225, 225, 225)
    pdf.set_x(x0)
    pdf.cell(45, 9, "TOTAL TTC :", fill=True, align="R")
    pdf.cell(30, 9, f"{total_ttc:.2f} {cur}", fill=True, align="R", new_x="LMARGIN", new_y="NEXT")

    # Notes / paiement
    if req.payment_info or req.notes:
        pdf.ln(7)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(4)
    if req.payment_info:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, "Modalités de paiement :", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, req.payment_info)
        pdf.ln(2)
    if req.notes:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, "Notes :", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, req.notes)

    # Pied de page
    pdf.set_y(-13)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(160, 160, 160)
    pdf.cell(0, 5, f"Facture générée via x402-invoice-gen — {req.company.name}", align="C")

    return bytes(pdf.output())


def _make_402(host: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "x402Version": 1,
            "error": "Payment required",
            "accepts": [{
                "scheme": "exact", "network": NETWORK,
                "maxAmountRequired": PRICE_ATOMIC,
                "resource": f"https://{host}/generate",
                "description": "Génération d'une facture PDF professionnelle (HT/TTC, multi-TVA)",
                "mimeType": "application/json",
                "payTo": PAY_TO, "maxTimeoutSeconds": 300,
                "asset": ASSET_ADDRESS,
                "extra": {"name": "USDC", "version": "2"},
            }],
        },
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/generate" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-invoice-gen.suretat.com"))
    return await call_next(request)


@app.get("/")
def root():
    return {
        "service": "x402 Invoice Generator",
        "protocol": "x402 (Base/USDC)",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/facture",
        "endpoint": "POST /generate",
        "output": "JSON + pdf_base64",
        "docs": "/docs",
    }


@app.post("/generate")
def generate(req: InvoiceRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    try:
        pdf_bytes = _build_pdf(req)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Génération PDF échouée : {e}"})
    subtotal_ht = sum(round(i.quantity * i.unit_price, 2) for i in req.items)
    total_tva = sum(round(i.quantity * i.unit_price * i.tva_rate / 100, 2) for i in req.items)
    return {
        "invoice_number": req.invoice.number,
        "total_ht": round(subtotal_ht, 2),
        "total_tva": round(total_tva, 2),
        "total_ttc": round(subtotal_ht + total_tva, 2),
        "currency": req.invoice.currency,
        "pdf_base64": base64.b64encode(pdf_bytes).decode(),
        "pdf_size_bytes": len(pdf_bytes),
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-invoice-gen.suretat.com")
    return {"x402Version": 1, "accepts": [{
        "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"https://{host}/generate",
        "description": "Génération d'une facture PDF professionnelle",
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
    uvicorn.run(app, host="0.0.0.0", port=3084, proxy_headers=True, forwarded_allow_ips="*")
