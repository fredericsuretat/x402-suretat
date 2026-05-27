# x402-suretat

Pay-per-use API microservices using the [x402 protocol](https://x402.org) — payments in USDC on Base mainnet.

## Architecture

Each service is a standalone FastAPI (Python) or Express (Node.js) microservice exposing a paid endpoint. Payment is handled via the `X-PAYMENT` header; no account or API key needed.

- **Network**: Base mainnet
- **Asset**: USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
- **payTo**: `0x6458941857a70C6cA18c440a316035A21901A12b`
- **Default price**: 0.0005 USDC/call

## Services

| Service | Port | Description |
|---|---|---|
| x402-adresses | 3033 | French address validation & geocoding |
| x402-barcode | 3050 | Barcode & QR generation |
| x402-base64 | 3065 | Base64 encode/decode |
| x402-color | 3068 | Color conversion & manipulation |
| x402-colorpalette | 3060 | Color palette extraction |
| x402-compress | 3077 | gzip/zlib/brotli/zip compress & decompress |
| x402-cron | 3057 | Cron expression parser |
| x402-csv2json | 3073 | CSV ↔ JSON conversion |
| x402-currency | 3051 | Currency conversion |
| x402-diff | 3072 | Text diff (unified/HTML/ndiff) |
| x402-dns | 3071 | DNS lookup (A/MX/TXT/CNAME/NS/SOA/PTR) |
| x402-email-validator | 3036 | Email validation |
| x402-fakedata-fr | 3045 | French fake data generator |
| x402-feries | 3063 | French public holidays |
| x402-geocoder-fr | 3032 | French geocoding (adresse.data.gouv.fr) |
| x402-hash | 3046 | MD5/SHA1/SHA256/SHA512/bcrypt hashing |
| x402-html2md | 3070 | URL/HTML → clean Markdown (Readability) |
| x402-iban | 3035 | IBAN validation & BIC lookup |
| x402-image-resize | 3076 | Image resize, crop, convert (Pillow) |
| x402-insee-fr | 3039 | INSEE communes data |
| x402-ipgeo | 3043 | IP geolocation |
| x402-jsonschema | 3054 | JSON Schema validation |
| x402-jwt | 3062 | JWT encode/decode/verify |
| x402-luhn | 3066 | Luhn algorithm check |
| x402-markdown | 3049 | Markdown → HTML |
| x402-mcp | — | MCP server exposing x402 tools for Claude |
| x402-num2words | 3044 | Number to words (fr/en) |
| x402-password | 3052 | Password strength & generation |
| x402-pdf-generator | 3041 | HTML/Markdown → PDF |
| x402-phone-fr | 3048 | French phone number validation |
| x402-qrcode | 3042 | QR code generation |
| x402-regex | 3059 | Regex test & extraction |
| x402-rss | 3058 | RSS/Atom feed parser |
| x402-scraper-api | 3034 | Web scraping to Markdown/JSON |
| x402-screenshot | 3075 | Webpage screenshots (Playwright) |
| x402-siret | 3031 | SIRET/SIREN lookup (INSEE) |
| x402-ssl | 3078 | SSL certificate checker |
| x402-subnet | 3053 | Subnet/CIDR calculator |
| x402-textstats | 3055 | Text statistics |
| x402-timezone | 3056 | Timezone conversion |
| x402-translate-fr | 3037 | French translation (DeepL) |
| x402-units | 3064 | Unit conversion |
| x402-urlmeta | 3047 | URL metadata extraction |
| x402-uuid | 3067 | UUID v1/v3/v4/v5 generation |
| x402-vat-fr | 3061 | French VAT number validation |
| x402-whois-fr | 3038 | WHOIS lookup |
| x402-xml2json | 3074 | XML ↔ JSON conversion |

## Quick start

```bash
cd services/x402-<name>
cp .env.example .env
docker compose up -d
```

## Live

All services available at `https://x402-<name>.suretat.com`
