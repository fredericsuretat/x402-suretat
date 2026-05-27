from __future__ import annotations
import json
import logging
import os
import time

import uvicorn
import xmltodict
from dicttoxml import dicttoxml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("x402-xml2json")

PRICE_ATOMIC  = os.getenv("PRICE_ATOMIC", "500")
PAY_TO        = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK       = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_requests": 0, "total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}

app = FastAPI(title="x402 XML <-> JSON", version="1.0.0")


class Xml2JsonRequest(BaseModel):
    xml: str = Field(..., description="XML content as string", max_length=5_000_000)
    force_list: list[str] | None = Field(default=None, description="Tag names that should always be a list")
    encoding: str = Field(default="utf-8", description="XML encoding")


class Json2XmlRequest(BaseModel):
    data: dict | list = Field(..., description="JSON object or array to convert to XML")
    root_element: str = Field(default="root", description="Name of the XML root element")
    item_element: str = Field(default="item", description="Name for array items (when data is a list)")
    pretty: bool = Field(default=True, description="Pretty-print the XML output")
    include_declaration: bool = Field(default=True, description="Include XML declaration header")


@app.get("/")
def root():
    return {
        "service": "x402 XML <-> JSON",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
        "endpoints": ["POST /xml2json", "POST /json2xml"],
        "tagline": "Convert XML to JSON or JSON to XML — handles attributes, namespaces, nested structures",
        "curl_example": "curl https://x402-xml2json.suretat.com/xml2json -H 'Content-Type: application/json' -d '{\"xml\": \"<person><name>Alice</name><age>30</age></person>\"}'",
        "try_it": "https://x402-xml2json.suretat.com/docs",
        "docs": "/docs",
    }


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


PAID_PATHS = {"/xml2json", "/json2xml"}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if request.url.path in PAID_PATHS and request.method == "POST":
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
                        "resource": "https://" + request.headers.get("host", "") + request.url.path,
                        "description": "XML <-> JSON conversion",
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


@app.post("/xml2json")
def xml_to_json(req: Xml2JsonRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    try:
        force_list = tuple(req.force_list) if req.force_list else None
        result = xmltodict.parse(
            req.xml,
            encoding=req.encoding,
            force_list=force_list,
            attr_prefix="@",
            cdata_key="#text",
        )
        return {"json": result}
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"XML parse error: {e}"})


@app.post("/json2xml")
def json_to_xml(req: Json2XmlRequest):
    stats["total_requests"] += 1
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000
    try:
        xml_bytes = dicttoxml(
            req.data,
            custom_root=req.root_element,
            item_func=lambda x: req.item_element,
            xml_declaration=req.include_declaration,
        )
        xml_str = xml_bytes.decode("utf-8")
        if req.pretty:
            import xml.dom.minidom
            xml_str = xml.dom.minidom.parseString(xml_bytes).toprettyxml(indent="  ")
            if not req.include_declaration:
                xml_str = "\n".join(xml_str.split("\n")[1:])
        return {"xml": xml_str}
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"Conversion error: {e}"})


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-xml2json.suretat.com")
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/xml2json",
            "description": "XML <-> JSON conversion",
            "mimeType": "application/json",
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS,
            "extra": {"name": "USDC", "version": "2"},
        }]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3074, proxy_headers=True, forwarded_allow_ips="*")
