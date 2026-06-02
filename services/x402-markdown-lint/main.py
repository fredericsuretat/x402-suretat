from __future__ import annotations
import logging
import os
import re
import time
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-markdown-lint")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 Markdown Lint & Format", version="1.0.0")


def lint_markdown(text: str) -> list[dict]:
    issues = []
    lines = text.splitlines()

    for i, line in enumerate(lines, 1):
        # Trailing whitespace
        if line != line.rstrip():
            issues.append({"line": i, "rule": "MD009", "severity": "warning", "message": "Trailing whitespace"})

        # Tabs instead of spaces
        if "\t" in line:
            issues.append({"line": i, "rule": "MD010", "severity": "warning", "message": "Hard tabs used"})

        # Line too long (>120 chars)
        if len(line) > 120:
            issues.append({"line": i, "rule": "MD013", "severity": "info", "message": f"Line too long ({len(line)} chars)"})

        # Heading with wrong format (## heading without space)
        m = re.match(r"^(#{1,6})([^ #\n])", line)
        if m:
            issues.append({"line": i, "rule": "MD018", "severity": "error", "message": f"Missing space after heading marker '{m.group(1)}'"})

        # Multiple consecutive blank lines (check with previous)
        if i > 2 and not line.strip() and not lines[i-2].strip():
            issues.append({"line": i, "rule": "MD012", "severity": "warning", "message": "Multiple consecutive blank lines"})

        # Bare URLs (not in link syntax)
        if re.search(r"(?<!\()(https?://\S+)(?!\))", line) and not re.search(r"!\[.*\]\(|<https?://", line):
            issues.append({"line": i, "rule": "MD034", "severity": "info", "message": "Bare URL found, consider using <url> or [text](url)"})

        # Emphasis used in headings
        if re.match(r"^#{1,6}\s.*[*_].*[*_]", line):
            issues.append({"line": i, "rule": "MD049", "severity": "warning", "message": "Emphasis used in heading"})

    # Missing blank line before heading
    for i in range(1, len(lines)):
        if re.match(r"^#{1,6}\s", lines[i]) and i > 0 and lines[i-1].strip():
            issues.append({"line": i+1, "rule": "MD022", "severity": "warning", "message": "Heading should be surrounded by blank lines"})

    # First line not a heading
    if lines and not re.match(r"^#{1,6}\s", lines[0].strip()):
        issues.append({"line": 1, "rule": "MD041", "severity": "info", "message": "First line should be a top-level heading"})

    return issues


def format_markdown(text: str) -> str:
    lines = text.splitlines()
    result = []
    prev_blank = False

    for i, line in enumerate(lines):
        # Remove trailing whitespace
        line = line.rstrip()
        # Convert tabs to 4 spaces
        line = line.replace("\t", "    ")

        # Ensure space after heading marker
        line = re.sub(r"^(#{1,6})([^ #\n])", r"\1 \2", line)

        is_blank = not line.strip()

        # Collapse multiple blank lines
        if is_blank and prev_blank:
            continue

        # Add blank line before headings
        if re.match(r"^#{1,6}\s", line) and result and not prev_blank:
            result.append("")

        result.append(line)
        prev_blank = is_blank

    # Remove trailing blank lines
    while result and not result[-1].strip():
        result.pop()

    # Add trailing newline
    return "\n".join(result) + "\n"


class LintRequest(BaseModel):
    text: str = Field(..., description="Markdown text to lint", max_length=500_000)
    fix: bool = Field(default=False, description="Also return auto-formatted version")


@app.get("/")
def root():
    return {
        "service": "x402 Markdown Lint & Format",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/call",
        "endpoint": "POST /lint",
        "rules": ["MD009", "MD010", "MD012", "MD013", "MD018", "MD022", "MD034", "MD041", "MD049"],
        "tagline": "Lint and auto-format Markdown — detect spacing, heading, URL and style issues",
        "curl_example": "curl https://x402-markdown-lint.suretat.com/lint -H 'Content-Type: application/json' -d '{\"text\": \"#Hello\\nThis is a test.\", \"fix\": true}'",
        "try_it": "https://x402-markdown-lint.suretat.com/docs",
        "docs": "/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


@app.get("/health")
async def health():
    return {"ok": True}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/lint" and request.method == "POST":
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
                        "resource": "https://" + request.headers.get("host", "") + "/lint",
                        "description": "Markdown lint and auto-format",
                        "mimeType": "application/json",
                        "payTo": PAY_TO,
                        "maxTimeoutSeconds": 300,
                        "asset": ASSET_ADDRESS,
                        "extra": {"name": "USDC", "version": "2"},
                    }],
                },
                headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
            )
    return await call_next(request)


@app.post("/lint")
def lint(req: LintRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    issues = lint_markdown(req.text)
    errors   = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    infos    = [i for i in issues if i["severity"] == "info"]

    result: dict = {
        "valid": len(errors) == 0,
        "issue_count": {"errors": len(errors), "warnings": len(warnings), "info": len(infos)},
        "issues": issues,
    }

    if req.fix:
        result["formatted"] = format_markdown(req.text)

    return result


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-markdown-lint.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/lint",
            "description": "Markdown lint and auto-format",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3082, proxy_headers=True, forwarded_allow_ips="*")
