# x402-suretat

Pay-per-use API microservices using the [x402 protocol](https://x402.org) — payments in USDC on Base mainnet. No API keys, no signup, no rate limits.

- **Network**: Base mainnet
- **Asset**: USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
- **payTo**: `0x6458941857a70C6cA18c440a316035A21901A12b`
- **Discovery**: each service exposes `/.well-known/x402.json` + FastAPI docs at `/docs`

## How it works

Send a `POST` to any endpoint — without an `X-PAYMENT` header you get a `402 Payment Required` response with payment details. Use an x402-compatible client to pay automatically:

```js
import { wrapFetch } from 'x402-fetch';
const fetch = wrapFetch({ privateKey: process.env.PRIVATE_KEY });
const res = await fetch('https://x402-hash.suretat.com/hash', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ text: 'hello world', algos: ['sha256'] }),
});
```

## Services

### 🇫🇷 French Data

| Service | URL | Price | Description |
|---------|-----|-------|-------------|
| x402-adresses | [x402-adresses.suretat.com](https://x402-adresses.suretat.com) | 0.001 USDC | Address validation & geocoding (adresse.data.gouv.fr) |
| x402-siret | [x402-siret.suretat.com](https://x402-siret.suretat.com) | 0.002 USDC | SIRET/SIREN company lookup (INSEE) |
| x402-iban | [x402-iban.suretat.com](https://x402-iban.suretat.com) | 0.0005 USDC | IBAN validation & BIC lookup |
| x402-geocoder-fr | [x402-geocoder-fr.suretat.com](https://x402-geocoder-fr.suretat.com) | 0.001 USDC | French geocoding with commune/département data |
| x402-email-validator | [x402-email-validator.suretat.com](https://x402-email-validator.suretat.com) | 0.001 USDC | Email validation with DNS MX check & disposable detection |
| x402-phone-fr | [x402-phone-fr.suretat.com](https://x402-phone-fr.suretat.com) | 0.0005 USDC | French phone number validation (E.164, carrier, region) |
| x402-insee-fr | [x402-insee-fr.suretat.com](https://x402-insee-fr.suretat.com) | 0.002 USDC | INSEE commune & département statistics |
| x402-vat | [x402-vat-fr.suretat.com](https://x402-vat-fr.suretat.com) | 0.0005 USDC | French VAT calculation & invoice breakdown |
| x402-feries | [x402-feries.suretat.com](https://x402-feries.suretat.com) | 0.0005 USDC | French public holidays (all 11 zones incl. overseas) |
| x402-fakedata-fr | [x402-fakedata-fr.suretat.com](https://x402-fakedata-fr.suretat.com) | 0.001 USDC | French synthetic data (persons, companies, addresses) |
| x402-translate-fr | [x402-translate-fr.suretat.com](https://x402-translate-fr.suretat.com) | 0.001 USDC | Translation via DeepL (30 languages, up to 5000 chars) |
| x402-whois-fr | [x402-whois-fr.suretat.com](https://x402-whois-fr.suretat.com) | 0.001 USDC | WHOIS for .fr & generic domains |
| x402-ipgeo | [x402-ipgeo.suretat.com](https://x402-ipgeo.suretat.com) | 0.001 USDC | IP geolocation (country, city, ISP, coordinates) |

### 🔐 Encoding & Crypto

| Service | URL | Price | Description |
|---------|-----|-------|-------------|
| x402-hash | [x402-hash.suretat.com](https://x402-hash.suretat.com) | 0.0005 USDC | MD5/SHA-1/SHA-256/SHA-512/SHA3/BLAKE2b/BLAKE2s |
| x402-base64 | [x402-base64.suretat.com](https://x402-base64.suretat.com) | 0.0005 USDC | Base64/Base64url/Base32/Base16/URL encode+decode |
| x402-uuid | [x402-uuid.suretat.com](https://x402-uuid.suretat.com) | 0.0005 USDC | UUID v1/v4/v5/v7 generation (up to 100/call), validate |
| x402-jwt | [x402-jwt.suretat.com](https://x402-jwt.suretat.com) | 0.0005 USDC | JWT decode/verify (HMAC, RSA, ECDSA) |
| x402-password | [x402-password.suretat.com](https://x402-password.suretat.com) | 0.0005 USDC | Password generation & zxcvbn strength scoring |
| x402-luhn | [x402-luhn.suretat.com](https://x402-luhn.suretat.com) | 0.0005 USDC | Luhn checksum for credit cards, IMEI |

### 📝 Text & Data

| Service | URL | Price | Description |
|---------|-----|-------|-------------|
| x402-markdown | [x402-markdown.suretat.com](https://x402-markdown.suretat.com) | 0.0005 USDC | Markdown → HTML (GFM: tables, task lists, autolinks) |
| x402-regex | [x402-regex.suretat.com](https://x402-regex.suretat.com) | 0.0005 USDC | Regex test/extract/replace/split with PCRE flags |
| x402-textstats | [x402-textstats.suretat.com](https://x402-textstats.suretat.com) | 0.0005 USDC | Readability scores (Flesch-Kincaid, Gunning Fog, SMOG) |
| x402-jsonschema | [x402-jsonschema.suretat.com](https://x402-jsonschema.suretat.com) | 0.0005 USDC | JSON Schema validation (Draft-07 / 2020-12) |
| x402-rss | [x402-rss.suretat.com](https://x402-rss.suretat.com) | 0.001 USDC | RSS 2.0/1.0 + Atom feed parsing |
| x402-urlmeta | [x402-urlmeta.suretat.com](https://x402-urlmeta.suretat.com) | 0.001 USDC | URL metadata: OG/Twitter Card/JSON-LD/canonical |
| x402-num2words | [x402-num2words.suretat.com](https://x402-num2words.suretat.com) | 0.0005 USDC | Number → words in 13 languages (fr, en, de, es, it…) |
| x402-html2md | [x402-html2md.suretat.com](https://x402-html2md.suretat.com) | 0.0005 USDC | URL/HTML → clean Markdown (Mozilla Readability) |
| x402-diff | [x402-diff.suretat.com](https://x402-diff.suretat.com) | 0.0005 USDC | Text diff: unified / HTML / ndiff |
| x402-csv2json | [x402-csv2json.suretat.com](https://x402-csv2json.suretat.com) | 0.0005 USDC | CSV ↔ JSON / NDJSON conversion |
| x402-xml2json | [x402-xml2json.suretat.com](https://x402-xml2json.suretat.com) | 0.0005 USDC | XML ↔ JSON conversion |

### 🧮 Math & Utils

| Service | URL | Price | Description |
|---------|-----|-------|-------------|
| x402-units | [x402-units.suretat.com](https://x402-units.suretat.com) | 0.0005 USDC | Unit conversion (length, mass, temp, volume, speed…) |
| x402-timezone | [x402-timezone.suretat.com](https://x402-timezone.suretat.com) | 0.0005 USDC | DST-aware timezone conversion (IANA) |
| x402-cron | [x402-cron.suretat.com](https://x402-cron.suretat.com) | 0.0005 USDC | Cron parser: next N runs, human description |
| x402-subnet | [x402-subnet.suretat.com](https://x402-subnet.suretat.com) | 0.0005 USDC | IPv4/IPv6 subnet calculator (network, broadcast, CIDR) |
| x402-currency | [x402-currency.suretat.com](https://x402-currency.suretat.com) | 0.001 USDC | Currency conversion (170+ currencies, real-time rates) |

### 🖼️ Visual & Media

| Service | URL | Price | Description |
|---------|-----|-------|-------------|
| x402-qrcode | [x402-qrcode.suretat.com](https://x402-qrcode.suretat.com) | 0.0005 USDC | QR code PNG/SVG with error correction & custom colors |
| x402-barcode | [x402-barcode.suretat.com](https://x402-barcode.suretat.com) | 0.0005 USDC | EAN-13/EAN-8/Code128/Code39/UPC-A barcodes PNG/SVG |
| x402-color | [x402-color.suretat.com](https://x402-color.suretat.com) | 0.0005 USDC | Color conversion HEX/RGB/HSL/HSV/CMYK + names |
| x402-colorpalette | [x402-colorpalette.suretat.com](https://x402-colorpalette.suretat.com) | 0.001 USDC | Dominant color palette from image URL |
| x402-pdf-generator | [x402-pdf-generator.suretat.com](https://x402-pdf-generator.suretat.com) | 0.005 USDC | HTML/Markdown → PDF, invoice/devis templates |
| x402-screenshot | [x402-screenshot.suretat.com](https://x402-screenshot.suretat.com) | 0.002 USDC | Webpage screenshot (Playwright, full-page, viewport) |
| x402-image-resize | [x402-image-resize.suretat.com](https://x402-image-resize.suretat.com) | 0.0005 USDC | Image resize, crop, convert (Pillow) |

### 🔧 Dev Tools

| Service | URL | Price | Description |
|---------|-----|-------|-------------|
| x402-compress | [x402-compress.suretat.com](https://x402-compress.suretat.com) | 0.0005 USDC | gzip/zlib/brotli/zip compress & decompress |
| x402-ssl | [x402-ssl.suretat.com](https://x402-ssl.suretat.com) | 0.0005 USDC | SSL certificate checker (expiry, chain, SANs) |
| x402-dns | [x402-dns.suretat.com](https://x402-dns.suretat.com) | 0.0005 USDC | DNS lookup A/MX/TXT/CNAME/NS/SOA/PTR |
| x402-scraper-api | [x402-scraper-api.suretat.com](https://x402-scraper-api.suretat.com) | 0.005 USDC | Web scraping → clean Markdown or structured JSON |
| x402-ip-tools | [x402-ip-tools.suretat.com](https://x402-ip-tools.suretat.com) | 0.0005 USDC | IP tools: validate, classify, PTR, ASN, bogon check |
| x402-phonetic | [x402-phonetic.suretat.com](https://x402-phonetic.suretat.com) | 0.0005 USDC | Phonetic encoding: Soundex, Metaphone, NYSIIS, Caverphone |
| x402-readability | [x402-readability.suretat.com](https://x402-readability.suretat.com) | 0.0005 USDC | Readability scoring (Flesch-Kincaid, SMOG, Gunning Fog) |
| x402-token-counter | [x402-token-counter.suretat.com](https://x402-token-counter.suretat.com) | 0.0005 USDC | Token counting for LLM context budgets (tiktoken) |
| x402-markdown-lint | [x402-markdown-lint.suretat.com](https://x402-markdown-lint.suretat.com) | 0.0005 USDC | Markdown lint & auto-format |

### 🔌 Integration

| Service | URL | Description |
|---------|-----|-------------|
| x402-mcp | — | MCP server exposing all x402 tools for Claude/AI agents |
| x402-suretat | [x402-suretat.suretat.com](https://x402-suretat.suretat.com) | Gateway & service discovery |

## Quick start

```bash
cd services/x402-hash
cp .env.example .env
docker compose up -d
```

## Discovery

- `GET /.well-known/x402.json` → payment metadata
- `GET /docs` → OpenAPI/Swagger UI
- `GET /health` → `{"status": "ok"}`
- `GET /stats` → call counts, revenue, uptime

## Infrastructure

Self-hosted on Base mainnet:
- **Toshiba** (x86_64, 4 GB RAM) — primary, all services
- **GCloud e2-micro** (1 GB) — failover for lightweight services
- **Oracle A1.Flex** (ARM64, 4 OCPU / 24 GB) — primary, most services
