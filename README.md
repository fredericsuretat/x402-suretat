# x402-suretat

**86 pay-per-use API micro-services** built on the [x402 protocol](https://x402.org) — payments in USDC on Base mainnet. No API keys. No signup. No rate limits. No subscription.

- **Protocol**: [x402](https://x402.org) (HTTP 402 Payment Required)
- **Network**: Base mainnet
- **Asset**: USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
- **payTo**: `0x6458941857a70C6cA18c440a316035A21901A12b`
- **Discovery**: each service exposes `/.well-known/x402.json` + Swagger UI at `/docs`

---

## How it works

Send a request without an `X-PAYMENT` header → get a `402 Payment Required` response with payment details. Use any x402-compatible client to pay automatically:

```js
import { wrapFetch } from '@x402/fetch';

const fetch = wrapFetch({ privateKey: process.env.PRIVATE_KEY });
const res = await fetch('https://x402-hash.suretat.com/hash', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ text: 'hello world', algos: ['sha256', 'blake2b'] }),
});
console.log(await res.json());
```

```python
from x402.clients.httpx import x402_httpx_client

async with x402_httpx_client(private_key=os.getenv("PRIVATE_KEY")) as client:
    r = await client.post("https://x402-qrcode.suretat.com/qrcode",
                          json={"text": "https://example.com", "format": "png"})
```

---

## Service Catalog

### 🇫🇷 French Data

| Service | Price | Description |
|---------|-------|-------------|
| [x402-adresses.suretat.com](https://x402-adresses.suretat.com) | 0.001 USDC | Validate & geocode French postal addresses (BAN API) |
| [x402-communes.suretat.com](https://x402-communes.suretat.com) | 0.0005 USDC | French communes data — name, INSEE code, department, population |
| [x402-fakedata-fr.suretat.com](https://x402-fakedata-fr.suretat.com) | 0.001 USDC | Generate realistic French fake data — names, SIRET, IBAN, addresses |
| [x402-feries.suretat.com](https://x402-feries.suretat.com) | 0.0005 USDC | French public holidays for any year, all 11 zones (metro + overseas) |
| [x402-geocoder-fr.suretat.com](https://x402-geocoder-fr.suretat.com) | 0.001 USDC | Geocode French addresses ↔ GPS coordinates (BAN/Nominatim) |
| [x402-iban.suretat.com](https://x402-iban.suretat.com) | 0.0005 USDC | Validate IBAN — all EU countries, returns BIC and bank info |
| [x402-insee-fr.suretat.com](https://x402-insee-fr.suretat.com) | 0.002 USDC | INSEE code lookup — commune, department, region data |
| [x402-naf.suretat.com](https://x402-naf.suretat.com) | 0.0005 USDC | NAF/APE code lookup — activity label and sector (French INSEE) |
| [x402-phone-fr.suretat.com](https://x402-phone-fr.suretat.com) | 0.0005 USDC | Validate/format French phone numbers — operator, type (mobile/fixed) |
| [x402-salary-estimator-fr.suretat.com](https://x402-salary-estimator-fr.suretat.com) | 0.001 USDC | Estimate French gross salary by job title, experience and region |
| [x402-siret.suretat.com](https://x402-siret.suretat.com) | 0.002 USDC | SIRET/SIREN lookup — legal name, address, NAF code, status |
| [x402-translate-fr.suretat.com](https://x402-translate-fr.suretat.com) | 0.001 USDC | Translate text to/from French via DeepL — 30+ languages, 5000 chars |
| [x402-tva-validate.suretat.com](https://x402-tva-validate.suretat.com) | 0.001 USDC | Validate French/EU TVA numbers + VIES lookup |
| [x402-vat-fr.suretat.com](https://x402-vat-fr.suretat.com) | 0.0005 USDC | French TVA calculation — HT↔TTC for all rates, invoice support |
| [x402-whois-fr.suretat.com](https://x402-whois-fr.suretat.com) | 0.001 USDC | WHOIS lookup for .fr and generic domains — registrar, dates, status |

### 🔐 Encoding & Cryptography

| Service | Price | Description |
|---------|-------|-------------|
| [x402-base64.suretat.com](https://x402-base64.suretat.com) | 0.0005 USDC | Encode/decode Base64, Base32, Base58, Base16, URL-safe variants |
| [x402-encrypt.suretat.com](https://x402-encrypt.suretat.com) | 0.001 USDC | Symmetric encryption/decryption: AES-256-GCM, ChaCha20-Poly1305 |
| [x402-hash.suretat.com](https://x402-hash.suretat.com) | 0.0005 USDC | Compute cryptographic hashes: MD5, SHA-1/256/512, SHA-3, BLAKE2 |
| [x402-hmac.suretat.com](https://x402-hmac.suretat.com) | 0.0005 USDC | Generate/verify HMAC signatures: SHA-256, SHA-512 |
| [x402-jwt.suretat.com](https://x402-jwt.suretat.com) | 0.0005 USDC | Decode, verify and sign JWT tokens (HS256, RS256) |
| [x402-luhn.suretat.com](https://x402-luhn.suretat.com) | 0.0005 USDC | Luhn checksum validation for credit cards, IMEI, ISIN |
| [x402-password.suretat.com](https://x402-password.suretat.com) | 0.0005 USDC | Generate secure passwords with custom rules + zxcvbn strength score |
| [x402-pwned.suretat.com](https://x402-pwned.suretat.com) | 0.0005 USDC | Check if a password/email appears in HaveIBeenPwned database |
| [x402-totp.suretat.com](https://x402-totp.suretat.com) | 0.0005 USDC | Generate and verify TOTP codes (RFC 6238) — 2FA compatible |
| [x402-uuid.suretat.com](https://x402-uuid.suretat.com) | 0.0005 USDC | Generate UUID v1/v3/v4/v5, validate and convert between formats |

### 📝 Text & Data

| Service | Price | Description |
|---------|-------|-------------|
| [x402-csv2json.suretat.com](https://x402-csv2json.suretat.com) | 0.0005 USDC | Convert CSV↔JSON array of objects, auto-typing, custom delimiter |
| [x402-diff.suretat.com](https://x402-diff.suretat.com) | 0.0005 USDC | Text diff: unified, HTML side-by-side, or line-by-line |
| [x402-html-sanitize.suretat.com](https://x402-html-sanitize.suretat.com) | 0.0005 USDC | Sanitize HTML — strip dangerous tags, custom allowlist |
| [x402-html2md.suretat.com](https://x402-html2md.suretat.com) | 0.0005 USDC | Convert URL or HTML → clean Markdown via Mozilla Readability |
| [x402-jsonpath.suretat.com](https://x402-jsonpath.suretat.com) | 0.0005 USDC | Query JSON with JSONPath expressions — returns matches + count |
| [x402-jsonschema.suretat.com](https://x402-jsonschema.suretat.com) | 0.0005 USDC | Validate JSON against JSON Schema (Draft-07 / 2020-12) |
| [x402-markdown.suretat.com](https://x402-markdown.suretat.com) | 0.0005 USDC | Convert Markdown to styled HTML (GFM: tables, task lists, autolinks) |
| [x402-num2words.suretat.com](https://x402-num2words.suretat.com) | 0.0005 USDC | Convert numbers to words in 13 languages (fr, en, de, es, it…) |
| [x402-phonetic.suretat.com](https://x402-phonetic.suretat.com) | 0.0005 USDC | Phonetic encoding: Soundex, Metaphone, Double Metaphone, NYSIIS, Caverphone |
| [x402-rss.suretat.com](https://x402-rss.suretat.com) | 0.001 USDC | Parse RSS 2.0 / Atom feeds → structured JSON with articles |
| [x402-xml2json.suretat.com](https://x402-xml2json.suretat.com) | 0.0005 USDC | Convert XML↔JSON — handles attributes, namespaces, nested structures |
| [x402-yaml2json.suretat.com](https://x402-yaml2json.suretat.com) | 0.0005 USDC | Convert YAML↔JSON bidirectionally |

### 💶 Finance

| Service | Price | Description |
|---------|-------|-------------|
| [x402-amortization.suretat.com](https://x402-amortization.suretat.com) | 0.0005 USDC | Amortization schedule for loans — monthly breakdown |
| [x402-crypto-price.suretat.com](https://x402-crypto-price.suretat.com) | 0.0005 USDC | Live crypto prices (BTC, ETH, etc.) via CoinGecko |
| [x402-currency.suretat.com](https://x402-currency.suretat.com) | 0.0005 USDC | Live currency conversion — 170+ currencies via ECB rates |
| [x402-invoice-gen.suretat.com](https://x402-invoice-gen.suretat.com) | 0.005 USDC | Generate invoice/devis PDF from structured data (French/EU format) |

### 🖼️ Visual & Media

| Service | Price | Description |
|---------|-------|-------------|
| [x402-avatar.suretat.com](https://x402-avatar.suretat.com) | 0.0005 USDC | Generate avatar images (initials, geometric, identicon) |
| [x402-barcode.suretat.com](https://x402-barcode.suretat.com) | 0.0005 USDC | Generate EAN-13, EAN-8, Code128, UPC-A barcodes as PNG/SVG |
| [x402-color.suretat.com](https://x402-color.suretat.com) | 0.0005 USDC | Convert colors between HEX, RGB, HSL, CMYK — get complementary/luminance |
| [x402-color-convert.suretat.com](https://x402-color-convert.suretat.com) | 0.0005 USDC | Advanced color conversions: HEX↔RGB↔HSL↔HSV↔LAB↔LCH↔XYZ |
| [x402-colorpalette.suretat.com](https://x402-colorpalette.suretat.com) | 0.001 USDC | Generate harmonious color palettes from a seed color |
| [x402-exif.suretat.com](https://x402-exif.suretat.com) | 0.001 USDC | Extract EXIF metadata from images (URL or base64) |
| [x402-image-info.suretat.com](https://x402-image-info.suretat.com) | 0.0005 USDC | Image metadata: format, dimensions, color mode, file size |
| [x402-image-resize.suretat.com](https://x402-image-resize.suretat.com) | 0.0005 USDC | Resize, crop, convert and filter images — JPEG, PNG, WebP, GIF, TIFF |
| [x402-pdf-generator.suretat.com](https://x402-pdf-generator.suretat.com) | 0.005 USDC | Convert HTML → PDF — headers, footers, custom page size |
| [x402-qrcode.suretat.com](https://x402-qrcode.suretat.com) | 0.0005 USDC | Generate QR codes as PNG or SVG — custom error correction and colors |
| [x402-screenshot.suretat.com](https://x402-screenshot.suretat.com) | 0.002 USDC | Full-page or viewport screenshot of any URL — PNG/JPEG via Playwright |
| [x402-svg2png.suretat.com](https://x402-svg2png.suretat.com) | 0.001 USDC | Convert SVG to PNG — custom dimensions, background color |

### 🌐 Network & Web

| Service | Price | Description |
|---------|-------|-------------|
| [x402-cert-info.suretat.com](https://x402-cert-info.suretat.com) | 0.001 USDC | TLS certificate details — issuer, SANs, validity, chain |
| [x402-country.suretat.com](https://x402-country.suretat.com) | 0.0005 USDC | Country info by code/name — capital, currency, region, TLD, dial code |
| [x402-dns.suretat.com](https://x402-dns.suretat.com) | 0.0005 USDC | DNS lookup: A, AAAA, MX, TXT, CNAME, NS, SOA, PTR for any domain |
| [x402-headers.suretat.com](https://x402-headers.suretat.com) | 0.0005 USDC | Inspect HTTP response headers for any URL |
| [x402-ip-tools.suretat.com](https://x402-ip-tools.suretat.com) | 0.0005 USDC | IP analysis: validate, classify, CIDR range, PTR, bogon check (v4/v6) |
| [x402-ipgeo.suretat.com](https://x402-ipgeo.suretat.com) | 0.001 USDC | Geolocate any IP — country, city, coordinates, ISP, ASN |
| [x402-redirect-chain.suretat.com](https://x402-redirect-chain.suretat.com) | 0.0005 USDC | Follow redirect chains for any URL — shows all hops with status codes |
| [x402-scraper-api.suretat.com](https://x402-scraper-api.suretat.com) | 0.005 USDC | Scrape any webpage → clean Markdown or structured JSON (JS-rendered) |
| [x402-social-meta.suretat.com](https://x402-social-meta.suretat.com) | 0.0005 USDC | Extract OG/Twitter Card/JSON-LD social metadata from any URL |
| [x402-ssl.suretat.com](https://x402-ssl.suretat.com) | 0.0005 USDC | SSL certificate checker — expiry, issuer, SANs, TLS version |
| [x402-subnet.suretat.com](https://x402-subnet.suretat.com) | 0.0005 USDC | CIDR subnet calculator — network, broadcast, usable hosts (v4/v6) |
| [x402-tech-detect.suretat.com](https://x402-tech-detect.suretat.com) | 0.002 USDC | Detect technologies used by any website (Wappalyzer-based) |
| [x402-urlmeta.suretat.com](https://x402-urlmeta.suretat.com) | 0.001 USDC | Extract URL metadata: title, description, og:image, HTTP headers |

### 🧠 NLP & AI

| Service | Price | Description |
|---------|-------|-------------|
| [x402-cv-parser.suretat.com](https://x402-cv-parser.suretat.com) | 0.001 USDC | Parse CV/resume text → structured JSON (contact, skills, education, XP) |
| [x402-doc-classifier.suretat.com](https://x402-doc-classifier.suretat.com) | 0.001 USDC | Classify document type: invoice, CV, contract, email, report… |
| [x402-french-nlp.suretat.com](https://x402-french-nlp.suretat.com) | 0.001 USDC | French NLP: tokenization, lemmatization, stopwords, NER, POS tagging |
| [x402-job-matcher.suretat.com](https://x402-job-matcher.suretat.com) | 0.001 USDC | Match job description vs candidate profile — score + key gaps |
| [x402-lang-detect.suretat.com](https://x402-lang-detect.suretat.com) | 0.0005 USDC | Detect language of any text — returns ISO code + confidence |
| [x402-readability.suretat.com](https://x402-readability.suretat.com) | 0.0005 USDC | Readability scores: Flesch-Kincaid, Gunning Fog, SMOG, Coleman-Liau, ARI |
| [x402-sentiment.suretat.com](https://x402-sentiment.suretat.com) | 0.001 USDC | Sentiment analysis: positive/negative/neutral + score |
| [x402-textstats.suretat.com](https://x402-textstats.suretat.com) | 0.0005 USDC | Text statistics: word count, sentence count, readability, frequency |

### 🔧 Dev Utilities

| Service | Price | Description |
|---------|-------|-------------|
| [x402-compress.suretat.com](https://x402-compress.suretat.com) | 0.0005 USDC | Compress/decompress with gzip, zlib, brotli or zip (base64 I/O) |
| [x402-cron.suretat.com](https://x402-cron.suretat.com) | 0.0005 USDC | Parse cron expressions — next N runs, human description (EN/FR) |
| [x402-curl2code.suretat.com](https://x402-curl2code.suretat.com) | 0.001 USDC | Convert curl commands to Python/JS/PHP/Go/Ruby code snippets |
| [x402-date-calc.suretat.com](https://x402-date-calc.suretat.com) | 0.0005 USDC | Date calculations — add/subtract, diff, next weekday, ISO week |
| [x402-email-validator.suretat.com](https://x402-email-validator.suretat.com) | 0.001 USDC | Validate email — syntax, MX DNS, disposable domain detection |
| [x402-http-status.suretat.com](https://x402-http-status.suretat.com) | 0.0005 USDC | HTTP status code reference — description, category, RFC |
| [x402-markdown-lint.suretat.com](https://x402-markdown-lint.suretat.com) | 0.0005 USDC | Lint and auto-format Markdown — detects heading, spacing, URL issues |
| [x402-regex.suretat.com](https://x402-regex.suretat.com) | 0.0005 USDC | Test regex patterns: matches, groups, named captures, flags |
| [x402-semver.suretat.com](https://x402-semver.suretat.com) | 0.0005 USDC | Parse, compare and validate semantic version strings |
| [x402-timezone.suretat.com](https://x402-timezone.suretat.com) | 0.0005 USDC | DST-aware datetime conversion across all IANA timezones |
| [x402-token-counter.suretat.com](https://x402-token-counter.suretat.com) | 0.0005 USDC | Count LLM tokens and estimate cost: GPT-4, Claude, LLaMA (tiktoken) |
| [x402-units.suretat.com](https://x402-units.suretat.com) | 0.0005 USDC | Unit conversion: length, weight, temp, pressure, speed, volume… |

---

## L402 Services

Two services use [L402](https://lightning.engineering/posts/2023-06-15-l402-lightning/) (Lightning + LSAT):

| Service | URL | Description |
|---------|-----|-------------|
| l402-ban-api | [l402-ban-api.suretat.com](https://l402-ban-api.suretat.com) | Spam/abuse reputation — check IP, email, domain against ban lists |
| l402-health-ctx | [l402-health-ctx.suretat.com](https://l402-health-ctx.suretat.com) | Health context API for AI agents — current infrastructure status |

---

## Discovery endpoints

Every service exposes:

```
GET /.well-known/x402.json   → payment metadata (price, payTo, network, asset)
GET /docs                    → Swagger / OpenAPI UI
GET /health                  → {"status": "ok", "version": "..."}
```

---

## Infrastructure

All 86 services run on **Oracle Cloud ARM** (A1.Flex, Always Free tier):
- **Host**: 88.96.59.82 (eu-paris-1, 1 OCPU / 12 GB RAM, ARM64)
- **Routing**: Traefik on Freebox VM → `x402-*.suretat.com` and `l402-*.suretat.com`
- **Uptime**: monitored via [frederic.suretat.com/lab](https://frederic.suretat.com/lab)

---

## Payment details

- **Network**: Base mainnet (chain ID 8453)
- **Asset**: USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
- **Wallet**: `0x6458941857a70C6cA18c440a316035A21901A12b`
- **Facilitator**: `https://x402.org/facilitator`

---

## License

MIT
