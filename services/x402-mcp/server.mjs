#!/usr/bin/env node
/**
 * x402-mcp — MCP server for x402 API services (suretat.com)
 *
 * Usage (no payment, free endpoints only):
 *   node server.mjs
 *
 * Usage (with x402 payment — 0.0005-0.005 USDC/call):
 *   WALLET_PRIVATE_KEY=0x... node server.mjs
 *
 * Config in Claude Code:
 *   claude mcp add x402 -- node /path/to/x402-mcp/server.mjs
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { wrapFetchWithPayment, x402Client } from "@x402/fetch";
import { registerExactEvmScheme } from "@x402/evm/exact/client";
import { privateKeyToAccount } from "viem/accounts";

// ── Payment setup ────────────────────────────────────────────────────────────

let x402Fetch = fetch;
const PRIVATE_KEY = process.env.WALLET_PRIVATE_KEY;

if (PRIVATE_KEY) {
  const account = privateKeyToAccount(PRIVATE_KEY);
  const client = new x402Client();
  registerExactEvmScheme(client, { signer: account });
  x402Fetch = wrapFetchWithPayment(fetch, client);
  process.stderr.write(`[x402-mcp] Payment enabled — wallet: ${account.address}\n`);
} else {
  process.stderr.write(`[x402-mcp] No wallet configured — paid endpoints will return 402 info\n`);
}

// ── Tool definitions ─────────────────────────────────────────────────────────

const TOOLS = [
  {
    name: "scrape_webpage",
    description:
      "Scrape any webpage and return its content as clean Markdown or structured JSON. " +
      "Handles JavaScript rendering. Useful for extracting articles, documentation, or data from any URL. " +
      "Cost: 0.005 USDC per call.",
    inputSchema: {
      type: "object",
      properties: {
        url: { type: "string", description: "URL of the page to scrape" },
        format: {
          type: "string",
          enum: ["markdown", "json"],
          description: "Output format: 'markdown' (clean text) or 'json' (structured data)",
          default: "markdown",
        },
        selector: {
          type: "string",
          description: "CSS selector to extract specific element (optional)",
        },
      },
      required: ["url"],
    },
    endpoint: "https://x402-scraper-api.suretat.com/scrape",
    price: "0.005 USDC",
  },
  {
    name: "generate_pdf",
    description:
      "Convert HTML content to a PDF document. Supports headers, footers, custom page formats. " +
      "Returns a base64-encoded PDF. Cost: 0.005 USDC per call.",
    inputSchema: {
      type: "object",
      properties: {
        html: { type: "string", description: "HTML content to convert to PDF" },
        format: {
          type: "string",
          enum: ["A4", "A3", "Letter", "Legal"],
          description: "Page format",
          default: "A4",
        },
        landscape: {
          type: "boolean",
          description: "Landscape orientation",
          default: false,
        },
        margin: {
          type: "string",
          description: "Margin in mm (e.g. '10' for 10mm all sides)",
          default: "10",
        },
      },
      required: ["html"],
    },
    endpoint: "https://x402-pdf-generator.suretat.com/generate",
    price: "0.005 USDC",
  },
  {
    name: "markdown_to_html",
    description:
      "Convert Markdown text to styled HTML. Supports tables, code highlighting, TOC, footnotes. " +
      "Can return a full HTML page with CSS or just the HTML fragment. Cost: 0.0005 USDC per call.",
    inputSchema: {
      type: "object",
      properties: {
        markdown: { type: "string", description: "Markdown text to convert" },
        wrap_html: {
          type: "boolean",
          description: "Wrap in a full HTML document with CSS styling",
          default: true,
        },
        titre: {
          type: "string",
          description: "Page title for the HTML document (used when wrap_html is true)",
        },
        format: {
          type: "string",
          enum: ["html", "json"],
          description: "'html' returns HTML string, 'json' returns {html, body_only, length}",
          default: "json",
        },
        extensions: {
          type: "array",
          items: { type: "string" },
          description: "Markdown extensions to enable",
          default: ["tables", "fenced_code", "codehilite", "toc", "nl2br"],
        },
      },
      required: ["markdown"],
    },
    endpoint: "https://x402-markdown.suretat.com/convert",
    price: "0.0005 USDC",
  },
  {
    name: "get_url_metadata",
    description:
      "Extract metadata from any URL: page title, description, og:image, Twitter card, " +
      "HTTP headers, redirect chain, canonical URL. Cost: 0.0005 USDC per call.",
    inputSchema: {
      type: "object",
      properties: {
        url: { type: "string", description: "URL to extract metadata from" },
        follow_redirects: {
          type: "boolean",
          description: "Follow HTTP redirects",
          default: true,
        },
        timeout: {
          type: "number",
          description: "Request timeout in seconds (1-30)",
          default: 10,
        },
      },
      required: ["url"],
    },
    endpoint: "https://x402-urlmeta.suretat.com/meta",
    price: "0.0005 USDC",
  },
  {
    name: "generate_qrcode",
    description:
      "Generate a QR code as PNG (base64) or SVG from any text, URL, phone number, or data. " +
      "Supports error correction levels and custom sizes. Cost: 0.0005 USDC per call.",
    inputSchema: {
      type: "object",
      properties: {
        data: { type: "string", description: "Text or URL to encode in the QR code" },
        format: {
          type: "string",
          enum: ["png", "svg"],
          description: "Output format: 'png' (base64) or 'svg' (SVG markup)",
          default: "png",
        },
        size: {
          type: "number",
          description: "Size in pixels for PNG (50–1000)",
          default: 300,
        },
        error_correction: {
          type: "string",
          enum: ["L", "M", "Q", "H"],
          description: "Error correction level: L (7%), M (15%), Q (25%), H (30%)",
          default: "M",
        },
      },
      required: ["data"],
    },
    endpoint: "https://x402-qrcode.suretat.com/qrcode",
    price: "0.0005 USDC",
  },
];

// ── Helper: call x402 service ─────────────────────────────────────────────────

async function callService(tool, args) {
  const response = await x402Fetch(tool.endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });

  if (response.status === 402) {
    const data = await response.json().catch(() => ({}));
    const req = data.accepts?.[0] ?? {};
    const price = req.maxAmountRequired
      ? (parseInt(req.maxAmountRequired) / 1_000_000).toFixed(4) + " USDC"
      : tool.price;
    return {
      content: [{
        type: "text",
        text:
          `⚠️  Payment required (${price})\n\n` +
          `Set WALLET_PRIVATE_KEY env var to enable automatic payment.\n\n` +
          `Service: ${req.resource ?? tool.endpoint}\n` +
          `Network: ${req.network ?? "base"}\n` +
          `Asset: USDC (${req.asset ?? "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"})\n` +
          `Pay to: ${req.payTo ?? "0x6458941857a70C6cA18c440a316035A21901A12b"}\n\n` +
          `Or use curl:\n${tool.name === "scrape_webpage"
            ? `curl ${tool.endpoint} -H 'Content-Type: application/json' -H 'X-PAYMENT: <token>' -d '${JSON.stringify(args)}'`
            : `curl ${tool.endpoint} -H 'Content-Type: application/json' -H 'X-PAYMENT: <token>' -d '${JSON.stringify(args)}'`
          }`,
      }],
    };
  }

  if (!response.ok) {
    const text = await response.text().catch(() => `HTTP ${response.status}`);
    throw new Error(`HTTP ${response.status}: ${text.substring(0, 200)}`);
  }

  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    const data = await response.json();
    // For QR/PDF that return base64 inline, limit output size
    if (tool.name === "generate_qrcode" && data.png_base64) {
      return {
        content: [
          { type: "text", text: `QR code generated successfully.\nFormat: ${data.format ?? "png"}\nSize: ${data.size ?? "?"}px\n\nBase64 PNG (${data.png_base64.length} chars):\n${data.png_base64.substring(0, 200)}...` },
        ],
      };
    }
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
  }

  if (contentType.includes("text/html")) {
    const html = await response.text();
    return { content: [{ type: "text", text: html.substring(0, 10000) }] };
  }

  if (contentType.includes("image/") || contentType.includes("application/pdf")) {
    const buffer = await response.arrayBuffer();
    const b64 = Buffer.from(buffer).toString("base64");
    return {
      content: [{
        type: "text",
        text: `Binary response (${contentType})\nSize: ${buffer.byteLength} bytes\nBase64 (first 200 chars): ${b64.substring(0, 200)}...`,
      }],
    };
  }

  const text = await response.text();
  return { content: [{ type: "text", text: text.substring(0, 5000) }] };
}

// ── MCP server ────────────────────────────────────────────────────────────────

const server = new Server(
  { name: "x402-suretat", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  const tool = TOOLS.find((t) => t.name === name);

  if (!tool) {
    return {
      content: [{ type: "text", text: `Unknown tool: ${name}` }],
      isError: true,
    };
  }

  try {
    return await callService(tool, args);
  } catch (err) {
    return {
      content: [{ type: "text", text: `Error: ${err.message}` }],
      isError: true,
    };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);
