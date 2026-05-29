from __future__ import annotations
import os
import re
import time
from typing import Any

import httpx
import uvicorn
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "2000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

HEADERS_UA = {
    "User-Agent": "Mozilla/5.0 (compatible; x402-tech-detect/1.0; +https://x402-tech-detect.suretat.com)",
    "Accept": "text/html,application/xhtml+xml",
}

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Tech Detector", version="1.0.0")

# ── Fingerprints ─────────────────────────────────────────────────────────────
# Chaque entrée : {name, category, confidence, checks}
# checks: list of {type, target, pattern}
#   type: "header" | "html" | "script" | "cookie" | "meta"
#   target: header name / meta name / attr / "body"
#   pattern: regex

FINGERPRINTS: list[dict[str, Any]] = [
    # CMS
    {"name": "WordPress", "category": "CMS", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"wp-content|wp-json|wp-includes"},
                {"type": "meta", "target": "generator", "pattern": r"WordPress"}]},
    {"name": "Drupal", "category": "CMS", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r'Drupal\.settings|drupal\.js|sites/default/files'},
                {"type": "header", "target": "X-Generator", "pattern": r"Drupal"}]},
    {"name": "Joomla", "category": "CMS", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"/components/com_|Joomla!"},
                {"type": "meta", "target": "generator", "pattern": r"Joomla"}]},
    {"name": "Wix", "category": "CMS", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"wix\.com|wixstatic\.com|_wix_"}]},
    {"name": "Squarespace", "category": "CMS", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"squarespace\.com|static\.squarespace"}]},
    {"name": "Webflow", "category": "CMS", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"webflow\.com"},
                {"type": "header", "target": "X-Powered-By", "pattern": r"Webflow"}]},
    {"name": "Ghost", "category": "CMS", "confidence": "high",
     "checks": [{"type": "meta", "target": "generator", "pattern": r"Ghost"},
                {"type": "html", "target": "body", "pattern": r"ghost\.org|content/themes/"}]},
    {"name": "Shopify", "category": "E-commerce", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"cdn\.shopify\.com|Shopify\.theme"},
                {"type": "header", "target": "X-ShopId", "pattern": r".+"}]},
    {"name": "WooCommerce", "category": "E-commerce", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"woocommerce|wc-cart|wc_add_to_cart"}]},
    {"name": "PrestaShop", "category": "E-commerce", "confidence": "high",
     "checks": [{"type": "meta", "target": "generator", "pattern": r"PrestaShop"},
                {"type": "html", "target": "body", "pattern": r"prestashop|PrestaShop"}]},
    # JS Frameworks
    {"name": "React", "category": "JavaScript Framework", "confidence": "medium",
     "checks": [{"type": "html", "target": "body", "pattern": r"react\.development\.js|react\.production\.min\.js|__REACT_DEVTOOLS|data-reactroot|data-reactid"}]},
    {"name": "Vue.js", "category": "JavaScript Framework", "confidence": "medium",
     "checks": [{"type": "html", "target": "body", "pattern": r"vue\.min\.js|vue\.js|__vue__|data-v-[a-f0-9]+"}]},
    {"name": "Angular", "category": "JavaScript Framework", "confidence": "medium",
     "checks": [{"type": "html", "target": "body", "pattern": r"ng-version|angular\.min\.js|ng-app|_nghost-"}]},
    {"name": "Next.js", "category": "JavaScript Framework", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"__NEXT_DATA__|/_next/static/"},
                {"type": "header", "target": "X-Powered-By", "pattern": r"Next\.js"}]},
    {"name": "Nuxt.js", "category": "JavaScript Framework", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"__NUXT__|/_nuxt/"},
                {"type": "header", "target": "X-Powered-By", "pattern": r"Nuxt"}]},
    {"name": "Svelte", "category": "JavaScript Framework", "confidence": "medium",
     "checks": [{"type": "html", "target": "body", "pattern": r"svelte-[a-z0-9]+|/__svelte"}]},
    {"name": "Gatsby", "category": "JavaScript Framework", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"gatsby-image|___gatsby|/page-data/"}]},
    # CSS Frameworks
    {"name": "Bootstrap", "category": "CSS Framework", "confidence": "medium",
     "checks": [{"type": "html", "target": "body", "pattern": r"bootstrap\.min\.css|bootstrap\.css|class=\"[^\"]*(?:container|navbar|btn btn-)"}]},
    {"name": "Tailwind CSS", "category": "CSS Framework", "confidence": "medium",
     "checks": [{"type": "html", "target": "body", "pattern": r"tailwindcss|class=\"[^\"]*(?:text-\w+-\d+|flex|grid|px-\d+|py-\d+)"}]},
    # Analytics
    {"name": "Google Analytics", "category": "Analytics", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"google-analytics\.com|googletagmanager\.com|gtag\(|_gaq\.push|UA-\d+-\d+|G-[A-Z0-9]+"}]},
    {"name": "Matomo", "category": "Analytics", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"matomo\.js|piwik\.js|_paq\.push"}]},
    {"name": "Plausible", "category": "Analytics", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"plausible\.io/js"}]},
    # CDN / Infrastructure
    {"name": "Cloudflare", "category": "CDN", "confidence": "high",
     "checks": [{"type": "header", "target": "CF-Ray", "pattern": r".+"},
                {"type": "header", "target": "Server", "pattern": r"cloudflare"}]},
    {"name": "Fastly", "category": "CDN", "confidence": "high",
     "checks": [{"type": "header", "target": "X-Served-By", "pattern": r"cache-[a-z]"},
                {"type": "header", "target": "Via", "pattern": r"varnish"}]},
    {"name": "AWS CloudFront", "category": "CDN", "confidence": "high",
     "checks": [{"type": "header", "target": "X-Amz-Cf-Id", "pattern": r".+"},
                {"type": "header", "target": "Via", "pattern": r"CloudFront"}]},
    # Web Servers
    {"name": "Nginx", "category": "Web Server", "confidence": "high",
     "checks": [{"type": "header", "target": "Server", "pattern": r"nginx"}]},
    {"name": "Apache", "category": "Web Server", "confidence": "high",
     "checks": [{"type": "header", "target": "Server", "pattern": r"Apache"}]},
    {"name": "Caddy", "category": "Web Server", "confidence": "high",
     "checks": [{"type": "header", "target": "Server", "pattern": r"Caddy"}]},
    # Backend
    {"name": "PHP", "category": "Backend", "confidence": "high",
     "checks": [{"type": "header", "target": "X-Powered-By", "pattern": r"PHP"},
                {"type": "header", "target": "Set-Cookie", "pattern": r"PHPSESSID"}]},
    {"name": "Django", "category": "Backend", "confidence": "medium",
     "checks": [{"type": "header", "target": "X-Frame-Options", "pattern": r"SAMEORIGIN"},
                {"type": "header", "target": "Set-Cookie", "pattern": r"csrftoken"},
                {"type": "html", "target": "body", "pattern": r"csrfmiddlewaretoken"}]},
    {"name": "Laravel", "category": "Backend", "confidence": "high",
     "checks": [{"type": "header", "target": "Set-Cookie", "pattern": r"laravel_session"},
                {"type": "header", "target": "X-Powered-By", "pattern": r"PHP"}]},
    {"name": "Ruby on Rails", "category": "Backend", "confidence": "high",
     "checks": [{"type": "header", "target": "X-Powered-By", "pattern": r"Phusion Passenger"},
                {"type": "header", "target": "Set-Cookie", "pattern": r"_session_id"}]},
    {"name": "ASP.NET", "category": "Backend", "confidence": "high",
     "checks": [{"type": "header", "target": "X-Powered-By", "pattern": r"ASP\.NET"},
                {"type": "header", "target": "X-AspNet-Version", "pattern": r".+"},
                {"type": "header", "target": "Set-Cookie", "pattern": r"ASP\.NET_SessionId"}]},
    # Misc
    {"name": "jQuery", "category": "JavaScript Library", "confidence": "medium",
     "checks": [{"type": "html", "target": "body", "pattern": r"jquery\.min\.js|jquery-[0-9.]+\.min\.js|jQuery\.fn\.jquery"}]},
    {"name": "Font Awesome", "category": "UI Library", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"fontawesome|font-awesome"}]},
    {"name": "Stripe", "category": "Payment", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"js\.stripe\.com|Stripe\.setPublishableKey"}]},
    {"name": "Intercom", "category": "Customer Support", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"intercom\.io|Intercom\("}]},
    {"name": "HubSpot", "category": "Marketing", "confidence": "high",
     "checks": [{"type": "html", "target": "body", "pattern": r"hs-scripts\.com|hubspot\.com"}]},
]


def _detect(html: str, resp_headers: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    body_text = str(soup)
    headers_lower = {k.lower(): v for k, v in resp_headers.items()}
    detected = []

    for fp in FINGERPRINTS:
        matched = False
        for check in fp["checks"]:
            if matched:
                break
            ctype = check["type"]
            pat = re.compile(check["pattern"], re.IGNORECASE)

            if ctype == "html":
                if pat.search(body_text):
                    matched = True
            elif ctype == "header":
                hkey = check["target"].lower()
                hval = headers_lower.get(hkey, "")
                if hval and pat.search(hval):
                    matched = True
            elif ctype == "meta":
                tag = soup.find("meta", attrs={"name": check["target"]})
                if not tag:
                    tag = soup.find("meta", attrs={"property": check["target"]})
                if tag and tag.get("content") and pat.search(tag["content"]):
                    matched = True
            elif ctype == "script":
                for s in soup.find_all("script", src=True):
                    if pat.search(s.get("src", "")):
                        matched = True
                        break
            elif ctype == "cookie":
                cookie_header = headers_lower.get("set-cookie", "")
                if pat.search(cookie_header):
                    matched = True

        if matched:
            detected.append({
                "name": fp["name"],
                "category": fp["category"],
                "confidence": fp["confidence"],
            })

    return detected


def _make_402(host: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "x402Version": 1, "error": "Payment required",
            "accepts": [{
                "scheme": "exact", "network": NETWORK,
                "maxAmountRequired": PRICE_ATOMIC,
                "resource": f"https://{host}/detect",
                "description": "Détection des technologies d'un site web (CMS, frameworks, analytics...)",
                "mimeType": "application/json",
                "payTo": PAY_TO, "maxTimeoutSeconds": 300,
                "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
            }],
        },
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/detect" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-tech-detect.suretat.com"))
    return await call_next(request)


class DetectRequest(BaseModel):
    url: str
    timeout: float = 10.0


@app.get("/")
def root():
    categories = sorted({fp["category"] for fp in FINGERPRINTS})
    return {
        "service": "x402 Tech Detector",
        "protocol": "x402 (Base/USDC)",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoint": "POST /detect",
        "fingerprints": len(FINGERPRINTS),
        "categories": categories,
        "docs": "/docs",
    }


@app.post("/detect")
async def detect(req: DetectRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if not req.url.startswith(("http://", "https://")):
        return JSONResponse(status_code=422, content={"error": "URL invalide"})

    try:
        async with httpx.AsyncClient(
            timeout=min(req.timeout, 15.0),
            follow_redirects=True,
            headers=HEADERS_UA,
        ) as client:
            resp = await client.get(req.url)
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": "Timeout"})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"Erreur réseau : {e}"})

    technologies = _detect(resp.text, dict(resp.headers))
    by_category: dict[str, list] = {}
    for tech in technologies:
        by_category.setdefault(tech["category"], []).append(tech["name"])

    return {
        "url": str(resp.url),
        "status_code": resp.status_code,
        "technologies_count": len(technologies),
        "technologies": technologies,
        "by_category": by_category,
        "server": resp.headers.get("Server") or resp.headers.get("server"),
        "powered_by": resp.headers.get("X-Powered-By") or resp.headers.get("x-powered-by"),
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-tech-detect.suretat.com")
    return {"x402Version": 1, "accepts": [{
        "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
        "resource": f"https://{host}/detect",
        "description": "Détection des technologies d'un site web",
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
    uvicorn.run(app, host="0.0.0.0", port=3088, proxy_headers=True, forwarded_allow_ips="*")
