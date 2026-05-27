from __future__ import annotations
import logging
import os
import time
from typing import Literal

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.toc import TocExtension
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-markdown")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
max-width:800px;margin:2rem auto;padding:0 1rem;color:#333;line-height:1.6}
h1,h2,h3{margin-top:1.5em;border-bottom:1px solid #eee;padding-bottom:.3em}
code{background:#f4f4f4;padding:.2em .4em;border-radius:3px;font-size:87%}
pre code{background:none;padding:0}
pre{background:#f4f4f4;padding:1em;border-radius:5px;overflow:auto}
blockquote{margin:0;padding:.5em 1em;border-left:4px solid #ddd;color:#666}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ddd;padding:.4em .8em;text-align:left}
th{background:#f4f4f4}
a{color:#0066cc}img{max-width:100%}
"""

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Markdown to HTML", version="1.0.0")


class MDRequest(BaseModel):
    markdown: str = Field(..., description="Texte Markdown à convertir", max_length=200_000)
    extensions: list[str] = Field(
        default=["tables", "fenced_code", "codehilite", "toc", "attr_list", "nl2br"],
        description="Extensions Markdown à activer",
    )
    wrap_html: bool = Field(default=True, description="Envelopper dans un document HTML complet avec CSS")
    titre: str | None = Field(default=None, description="Titre de la page (si wrap_html=True)")
    format: Literal["html", "json"] = Field(default="html", description="Format de réponse")


@app.get("/")
def root():
    return {
        "service": "x402 Markdown to HTML",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.0005 USDC/conversion",
        "endpoint": "POST /convert",
        "extensions": ["tables", "fenced_code", "codehilite", "toc", "attr_list", "nl2br", "footnotes", "admonition"],
        "docs": "/docs",
        "tagline": "Convert Markdown text to styled HTML — instantly",
        "curl_example": "curl https://x402-markdown.suretat.com/convert -H 'Content-Type: application/json' -d '{\"markdown\": \"# Hello\\n**World** — *formatted*\"}'",
        "try_it": "https://x402-markdown.suretat.com/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/convert" and request.method == "POST":
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
                        "resource": "https://" + request.headers.get("host", str(request.url.hostname)) + str(request.url.path),
                        "description": "Markdown to HTML — 0.0005 USDC",
                        "mimeType": "text/html",
                        "payTo": PAY_TO,
                        "maxTimeoutSeconds": 300,
                        "asset": ASSET_ADDRESS,
                        "extra": {"name": "USDC", "version": "2"},
                    }],
                },
                headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
            )
    return await call_next(request)


@app.post("/convert")
def convert_md(req: MDRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    valid_exts = {
        "tables", "fenced_code", "codehilite", "toc", "attr_list",
        "nl2br", "footnotes", "admonition", "meta", "abbr", "def_list",
    }
    exts = [e for e in req.extensions if e in valid_exts]
    if "codehilite" in exts:
        exts = [e for e in exts if e != "codehilite"]
        exts.append(CodeHiliteExtension(guess_lang=False, noclasses=True))

    try:
        md = markdown.Markdown(extensions=exts)
        body_html = md.convert(req.markdown)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

    if req.wrap_html:
        titre = req.titre or "Document"
        full_html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titre}</title>
<style>{CSS}</style>
</head>
<body>
{body_html}
</body>
</html>"""
        if req.format == "html":
            return Response(content=full_html, media_type="text/html; charset=utf-8")
        return {"html": full_html, "body_only": body_html, "length": len(full_html)}

    if req.format == "html":
        return Response(content=body_html, media_type="text/html; charset=utf-8")
    return {"html": body_html, "length": len(body_html)}



@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK if "NETWORK" in dir() else os.getenv("NETWORK", "base"),
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/convert",
            "description": "x402 Markdown to HTML",
            "mimeType": "application/json",
            "payTo": PAY_TO if "PAY_TO" in dir() else os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b"),
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS if "ASSET_ADDRESS" in dir() else "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "extra": {"name": "USDC", "version": "2"},
        }]
    }

@app.get("/.well-known/x402")
async def x402_well_known_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/.well-known/x402.json")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3049)
