from __future__ import annotations
import os, time, re, shlex, json
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Curl2Code", version="1.0.0")

SUPPORTED_LANGS = {"python", "javascript", "php", "go", "ruby"}


def parse_curl(curl_cmd: str) -> dict:
    """Parse a curl command string into components."""
    # Normalize multiline
    curl_cmd = curl_cmd.replace("\\\n", " ").replace("\\\r\n", " ")

    try:
        tokens = shlex.split(curl_cmd)
    except ValueError:
        # Fallback: simple split
        tokens = curl_cmd.split()

    if tokens and tokens[0].lower() in ("curl", "curl.exe"):
        tokens = tokens[1:]

    url = None
    method = None
    headers: Dict[str, str] = {}
    data = None
    form_data: Dict[str, str] = {}
    follow_redirects = False
    insecure = False

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok in ("-X", "--request"):
            i += 1
            if i < len(tokens):
                method = tokens[i].upper()

        elif tok in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                hdr = tokens[i]
                if ":" in hdr:
                    k, v = hdr.split(":", 1)
                    headers[k.strip()] = v.strip()

        elif tok in ("-d", "--data", "--data-raw", "--data-binary"):
            i += 1
            if i < len(tokens):
                data = tokens[i]

        elif tok in ("-F", "--form"):
            i += 1
            if i < len(tokens):
                kv = tokens[i]
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    form_data[k] = v

        elif tok in ("-L", "--location"):
            follow_redirects = True

        elif tok in ("-k", "--insecure"):
            insecure = True

        elif not tok.startswith("-"):
            url = tok

        i += 1

    if not method:
        method = "POST" if (data or form_data) else "GET"

    # Try to parse data as JSON
    json_body = None
    if data:
        try:
            json_body = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            pass

    return {
        "url": url or "",
        "method": method,
        "headers": headers,
        "data": data,
        "json_body": json_body,
        "form_data": form_data,
        "follow_redirects": follow_redirects,
        "insecure": insecure,
    }


def to_python(p: dict) -> str:
    lines = ["import requests", ""]
    if p["headers"]:
        lines.append("headers = {")
        for k, v in p["headers"].items():
            lines.append(f'    "{k}": "{v}",')
        lines.append("}")
        lines.append("")

    method = p["method"].lower()

    if p["json_body"] is not None:
        lines.append(f"payload = {json.dumps(p['json_body'], indent=4)}")
        lines.append("")
        args = f'"{p["url"]}"'
        kwargs = ", headers=headers" if p["headers"] else ""
        kwargs += ", json=payload"
        lines.append(f'response = requests.{method}({args}{kwargs})')
    elif p["form_data"]:
        lines.append("form_data = {")
        for k, v in p["form_data"].items():
            lines.append(f'    "{k}": "{v}",')
        lines.append("}")
        lines.append("")
        args = f'"{p["url"]}"'
        kwargs = ", headers=headers" if p["headers"] else ""
        kwargs += ", data=form_data"
        lines.append(f'response = requests.{method}({args}{kwargs})')
    elif p["data"]:
        lines.append(f'data = {repr(p["data"])}')
        lines.append("")
        args = f'"{p["url"]}"'
        kwargs = ", headers=headers" if p["headers"] else ""
        kwargs += ", data=data"
        lines.append(f'response = requests.{method}({args}{kwargs})')
    else:
        args = f'"{p["url"]}"'
        kwargs = ", headers=headers" if p["headers"] else ""
        lines.append(f'response = requests.{method}({args}{kwargs})')

    lines.append("")
    lines.append("print(response.status_code)")
    lines.append("print(response.json())")
    return "\n".join(lines)


def to_javascript(p: dict) -> str:
    lines = []
    headers_str = json.dumps(p["headers"], indent=2) if p["headers"] else "{}"

    if p["json_body"] is not None:
        body_str = json.dumps(p["json_body"], indent=2)
        lines.append(f"""const response = await fetch("{p['url']}", {{
  method: "{p['method']}",
  headers: {headers_str},
  body: JSON.stringify({body_str}),
}});

const data = await response.json();
console.log(data);""")
    elif p["data"]:
        lines.append(f"""const response = await fetch("{p['url']}", {{
  method: "{p['method']}",
  headers: {headers_str},
  body: {repr(p['data'])},
}});

const data = await response.json();
console.log(data);""")
    else:
        lines.append(f"""const response = await fetch("{p['url']}", {{
  method: "{p['method']}",
  headers: {headers_str},
}});

const data = await response.json();
console.log(data);""")

    return "\n".join(lines)


def to_php(p: dict) -> str:
    lines = ["<?php", "$ch = curl_init();", ""]
    lines.append(f'curl_setopt($ch, CURLOPT_URL, "{p["url"]}");')
    lines.append("curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);")

    if p["method"] != "GET":
        lines.append(f'curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "{p["method"]}");')

    if p["headers"]:
        hdrs = [f'"{k}: {v}"' for k, v in p["headers"].items()]
        lines.append(f'curl_setopt($ch, CURLOPT_HTTPHEADER, [{", ".join(hdrs)}]);')

    if p["json_body"] is not None:
        lines.append(f'curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode({json.dumps(p["json_body"])}));')
    elif p["data"]:
        lines.append(f'curl_setopt($ch, CURLOPT_POSTFIELDS, {repr(p["data"])});')

    lines.append("")
    lines.append("$response = curl_exec($ch);")
    lines.append("curl_close($ch);")
    lines.append("echo $response;")
    lines.append("?>")
    return "\n".join(lines)


def to_go(p: dict) -> str:
    lines = [
        'package main',
        '',
        'import (',
        '    "fmt"',
        '    "io"',
        '    "net/http"',
        '    "strings"',
    ]
    if p["json_body"] is not None or p["data"]:
        pass
    lines.append(')')
    lines.append('')
    lines.append('func main() {')

    if p["json_body"] is not None:
        body_json = json.dumps(p["json_body"])
        lines.append(f'    body := strings.NewReader(`{body_json}`)')
        lines.append(f'    req, _ := http.NewRequest("{p["method"]}", "{p["url"]}", body)')
    elif p["data"]:
        lines.append(f'    body := strings.NewReader("{p["data"]}")')
        lines.append(f'    req, _ := http.NewRequest("{p["method"]}", "{p["url"]}", body)')
    else:
        lines.append(f'    req, _ := http.NewRequest("{p["method"]}", "{p["url"]}", nil)')

    for k, v in p["headers"].items():
        lines.append(f'    req.Header.Set("{k}", "{v}")')

    lines.append('    client := &http.Client{}')
    lines.append('    resp, err := client.Do(req)')
    lines.append('    if err != nil { panic(err) }')
    lines.append('    defer resp.Body.Close()')
    lines.append('    data, _ := io.ReadAll(resp.Body)')
    lines.append('    fmt.Println(string(data))')
    lines.append('}')
    return "\n".join(lines)


def to_ruby(p: dict) -> str:
    lines = [
        "require 'net/http'",
        "require 'json'",
        "require 'uri'",
        "",
        f'uri = URI.parse("{p["url"]}")',
        f'http = Net::HTTP.new(uri.host, uri.port)',
        "http.use_ssl = true if uri.scheme == 'https'",
        "",
    ]

    method_class = {
        "GET": "Net::HTTP::Get",
        "POST": "Net::HTTP::Post",
        "PUT": "Net::HTTP::Put",
        "PATCH": "Net::HTTP::Patch",
        "DELETE": "Net::HTTP::Delete",
    }.get(p["method"], "Net::HTTP::Get")

    lines.append(f'request = {method_class}.new(uri.request_uri)')

    for k, v in p["headers"].items():
        lines.append(f'request["{k}"] = "{v}"')

    if p["json_body"] is not None:
        lines.append(f'request.body = {json.dumps(p["json_body"])}.to_json')
    elif p["data"]:
        lines.append(f'request.body = {repr(p["data"])}')

    lines.append("")
    lines.append("response = http.request(request)")
    lines.append("puts response.body")
    return "\n".join(lines)


CONVERTERS = {
    "python": to_python,
    "javascript": to_javascript,
    "php": to_php,
    "go": to_go,
    "ruby": to_ruby,
}


def _make_402(host: str, endpoint: str = "/convert") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "Convert curl command to Python/JS/PHP/Go/Ruby code",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path == "/convert" and request.method == "POST":
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-curl2code.suretat.com"))
    return await call_next(request)


class ConvertRequest(BaseModel):
    curl: str
    lang: str


@app.get("/")
def root():
    return {"service": "x402 Curl2Code", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
            "supported_langs": list(SUPPORTED_LANGS), "docs": "/docs"}


@app.post("/convert")
def convert(req: ConvertRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    lang = req.lang.lower()
    if lang not in SUPPORTED_LANGS:
        return JSONResponse(status_code=400, content={"error": f"lang must be one of: {', '.join(SUPPORTED_LANGS)}"})

    try:
        parsed = parse_curl(req.curl)
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Failed to parse curl: {str(e)}"})

    code = CONVERTERS[lang](parsed)

    return {
        "lang": lang,
        "code": code,
        "parsed": {
            "url": parsed["url"],
            "method": parsed["method"],
            "headers_count": len(parsed["headers"]),
            "has_body": bool(parsed["data"] or parsed["json_body"]),
        },
    }


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-curl2code.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/convert",
        "description": "Convert curl command to Python/JS/PHP/Go/Ruby code",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3110, proxy_headers=True, forwarded_allow_ips="*")
