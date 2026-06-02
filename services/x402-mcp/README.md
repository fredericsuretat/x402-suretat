# @fredericsuretat/x402-mcp

MCP server for [x402 pay-per-use API services](https://frederic.suretat.com/llms.txt).  
Pay **USDC on Base** — no API keys, no signup, no rate limits. AI agents pay autonomously.

## Installation

```bash
npx @fredericsuretat/x402-mcp
```

Or add to your Claude Code config:

```json
{
  "mcpServers": {
    "x402": {
      "command": "npx",
      "args": ["@fredericsuretat/x402-mcp"],
      "env": {
        "WALLET_PRIVATE_KEY": "0x..."
      }
    }
  }
}
```

## Tools

| Tool | Description | Cost |
|------|-------------|------|
| `scrape_webpage` | Scrape any URL → clean Markdown or JSON | 0.005 USDC |
| `generate_pdf` | HTML → PDF (A4/A3/Letter, headers, footers) | 0.005 USDC |
| `markdown_to_html` | Markdown → styled HTML with GFM, tables, syntax highlighting | 0.0005 USDC |
| `get_url_metadata` | Extract OG/Twitter Card/JSON-LD metadata from any URL | 0.0005 USDC |
| `generate_qrcode` | Generate QR code as PNG (base64) or SVG | 0.0005 USDC |

## Without a wallet

Works without `WALLET_PRIVATE_KEY` — tools return payment details (price, address, network) instead of calling the service.

## Full catalog

38+ services live: https://frederic.suretat.com/llms.txt

Payment wallet: `0x6458941857a70C6cA18c440a316035A21901A12b` (USDC on Base mainnet)
