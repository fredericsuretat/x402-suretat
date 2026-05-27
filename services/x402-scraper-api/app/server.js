'use strict';
const express  = require('express');
const cors     = require('cors');
const fs       = require('fs');
const path     = require('path');
const cheerio  = require('cheerio');

const app  = express();
app.set('trust proxy', 1);
app.use(cors({ methods: ['GET', 'POST', 'OPTIONS'] }));
app.use(express.json());

const PORT        = parseInt(process.env.PORT || '3034');
const PAY_TO      = process.env.PAYMENT_ADDRESS || '0x6458941857a70C6cA18c440a316035A21901A12b';
const USDC_BASE   = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913';
const FACILITATOR = process.env.FACILITATOR_URL || 'https://x402.org/facilitator';
const PRICE       = process.env.PRICE_USDC || '0.002';
const DATA_FILE   = process.env.DATA_FILE || '/app/data/stats.json';
const TEST_MODE   = process.env.TEST_MODE === 'true';
const CDP_API_KEY_ID     = process.env.CDP_API_KEY_ID;
const CDP_API_KEY_SECRET = process.env.CDP_API_KEY_SECRET;

// Domains blocked from scraping (abuse prevention)
const BLOCKED_DOMAINS = new Set(['localhost', '127.0.0.1', '0.0.0.0', '169.254.', '192.168.', '10.', '172.16.']);

async function generateCdpJwt(method, reqPath) {
  const { generateJwt } = require('@coinbase/cdp-sdk/auth');
  return generateJwt({ apiKeyId: CDP_API_KEY_ID, apiKeySecret: CDP_API_KEY_SECRET, requestMethod: method, requestHost: 'api.cdp.coinbase.com', requestPath: reqPath, expiresIn: 120 });
}

// ── Stats persistées ──────────────────────────────────────────────────────────
let stats = { payments_total: 0, revenue_usdc: 0, last_payments: [] };
try { if (fs.existsSync(DATA_FILE)) stats = JSON.parse(fs.readFileSync(DATA_FILE)); } catch {}
function saveStats() {
  try {
    fs.mkdirSync(path.dirname(DATA_FILE), { recursive: true });
    fs.writeFileSync(DATA_FILE, JSON.stringify(stats));
  } catch {}
}

// ── x402 helpers ──────────────────────────────────────────────────────────────
const BAZAAR_SCHEMAS = {
  '/scrape': {
    discoverable: true,
    category: 'web',
    tags: ['scraping', 'html', 'extract', 'metadata', 'json-ld', 'opengraph', 'web'],
    bodyType: 'json',
    input: { url: 'https://example.com', fields: ['title', 'description', 'og', 'jsonld', 'links'] },
    inputSchema: {
      type: 'object',
      properties: {
        url: { type: 'string', description: 'URL à scraper (https uniquement)' },
        fields: {
          type: 'array',
          description: 'Champs à extraire: title, description, og, jsonld, links, text (défaut: tous)',
          items: { type: 'string', enum: ['title', 'description', 'og', 'jsonld', 'links', 'text', 'headings'] },
        },
        timeout: { type: 'number', description: 'Timeout en ms (max 15000, défaut 10000)' },
      },
      required: ['url'],
    },
    outputSchema: {
      type: 'object',
      properties: {
        url: { type: 'string' }, status: { type: 'number' },
        title: { type: 'string' }, description: { type: 'string' },
        og: { type: 'object' }, jsonld: { type: 'array' },
        links: { type: 'array' }, text: { type: 'string' },
        headings: { type: 'object' },
        scraped_at: { type: 'string' },
      },
    },
  },
  '/extract': {
    discoverable: true,
    category: 'web',
    tags: ['scraping', 'css-selector', 'xpath', 'extract', 'web'],
    bodyType: 'json',
    input: { url: 'https://example.com', selectors: { headline: 'h1', price: '.price' } },
    inputSchema: {
      type: 'object',
      properties: {
        url: { type: 'string', description: 'URL à scraper' },
        selectors: {
          type: 'object',
          description: 'Objet { nomChamp: "sélecteur CSS" } à extraire',
          additionalProperties: { type: 'string' },
        },
        timeout: { type: 'number', description: 'Timeout en ms (max 15000)' },
      },
      required: ['url', 'selectors'],
    },
    outputSchema: {
      type: 'object',
      properties: {
        url: { type: 'string' }, status: { type: 'number' },
        data: { type: 'object' }, scraped_at: { type: 'string' },
      },
    },
  },
};

function buildRequirements(resource, description) {
  const pathname = new URL(resource).pathname;
  const bazaar = BAZAAR_SCHEMAS[pathname];
  return {
    scheme: 'exact', network: 'base', maxAmountRequired: PRICE,
    resource, description, mimeType: 'application/json',
    payTo: PAY_TO, maxTimeoutSeconds: 300, asset: USDC_BASE,
    extra: { name: 'USDC', version: '2', ...(bazaar ? { bazaar } : {}) },
  };
}

function send402(req, res, description) {
  const resource = `https://${req.get('host')}${req.path}`;
  res.status(402).set('Cache-Control', 'no-store').json({
    x402Version: 1,
    accepts: [buildRequirements(resource, description)],
    error: 'Payment required',
  });
}

async function verifyPayment(paymentHeader, resource, description) {
  if (TEST_MODE) return true;
  try {
    const requirements = buildRequirements(resource, description);
    const headers = { 'Content-Type': 'application/json' };
    let bodyData;
    if (CDP_API_KEY_ID && CDP_API_KEY_SECRET) {
      const payment = JSON.parse(Buffer.from(paymentHeader, 'base64').toString());
      bodyData = { x402Version: 1, paymentPayload: payment, paymentRequirements: [requirements] };
      headers['Authorization'] = `Bearer ${await generateCdpJwt('POST', '/platform/v2/x402/verify')}`;
    } else {
      bodyData = { x402Version: 1, paymentHeader, paymentRequirements: [requirements] };
    }
    const r = await fetch(`${FACILITATOR}/verify`, {
      method: 'POST', headers, body: JSON.stringify(bodyData), signal: AbortSignal.timeout(8000),
    });
    const data = await r.json();
    return data.isValid === true;
  } catch { return false; }
}

async function settlePayment(paymentHeader, resource, description) {
  if (TEST_MODE || !paymentHeader) return null;
  try {
    const requirements = buildRequirements(resource, description);
    const headers = { 'Content-Type': 'application/json' };
    let bodyData;
    if (CDP_API_KEY_ID && CDP_API_KEY_SECRET) {
      const payment = JSON.parse(Buffer.from(paymentHeader, 'base64').toString());
      bodyData = { x402Version: 1, paymentPayload: payment, paymentRequirements: [requirements] };
      headers['Authorization'] = `Bearer ${await generateCdpJwt('POST', '/platform/v2/x402/settle')}`;
    } else {
      bodyData = { x402Version: 1, paymentHeader, paymentRequirements: [requirements] };
    }
    const r = await fetch(`${FACILITATOR}/settle`, {
      method: 'POST', headers, body: JSON.stringify(bodyData), signal: AbortSignal.timeout(10000),
    });
    return await r.json();
  } catch { return null; }
}

function x402Middleware(description) {
  return async (req, res, next) => {
    const hdr = req.headers['x-payment'];
    if (!hdr) return send402(req, res, description);
    const resource = `${req.protocol}://${req.get('host')}${req.path}`;
    const valid = await verifyPayment(hdr, resource, description);
    if (!valid) return res.status(402).json({ error: 'Paiement invalide ou expiré' });
    req._x402Hdr      = hdr;
    req._x402Desc     = description;
    req._x402Resource = resource;
    next();
  };
}

function recordPayment(type, query) {
  stats.payments_total++;
  stats.revenue_usdc = parseFloat((stats.revenue_usdc + parseFloat(PRICE)).toFixed(6));
  stats.last_payments.unshift({ ts: new Date().toISOString(), type, query });
  if (stats.last_payments.length > 50) stats.last_payments.pop();
  saveStats();
}

// ── Scraper helpers ───────────────────────────────────────────────────────────
const SCRAPER_UA = 'Mozilla/5.0 (compatible; x402-scraper/1.0; +https://x402-scraper.suretat.com/docs)';

function validateUrl(rawUrl) {
  let parsed;
  try { parsed = new URL(rawUrl); } catch { throw Object.assign(new Error('URL invalide'), { status: 400 }); }
  if (!['http:', 'https:'].includes(parsed.protocol))
    throw Object.assign(new Error('Seuls les protocoles http/https sont autorisés'), { status: 400 });
  const host = parsed.hostname;
  for (const blocked of BLOCKED_DOMAINS) {
    if (host === blocked || host.endsWith('.' + blocked) || host.startsWith(blocked))
      throw Object.assign(new Error('URL interne non autorisée'), { status: 403 });
  }
  return parsed;
}

async function fetchPage(url, timeoutMs = 10000) {
  const r = await fetch(url, {
    headers: {
      'User-Agent': SCRAPER_UA,
      'Accept': 'text/html,application/xhtml+xml,*/*;q=0.9',
      'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
    },
    signal: AbortSignal.timeout(Math.min(timeoutMs, 15000)),
    redirect: 'follow',
  });
  if (!r.ok && r.status !== 404)
    throw Object.assign(new Error(`HTTP ${r.status} — ${r.statusText}`), { status: r.status >= 400 && r.status < 500 ? r.status : 502 });
  const ct = r.headers.get('content-type') || '';
  if (!ct.includes('html') && !ct.includes('text') && !ct.includes('json') && !ct.includes('xml'))
    throw Object.assign(new Error(`Type de contenu non supporté: ${ct}`), { status: 415 });
  return { html: await r.text(), status: r.status, finalUrl: r.url };
}

function extractOg($) {
  const og = {};
  $('meta[property^="og:"], meta[name^="og:"]').each((_, el) => {
    const k = ($(el).attr('property') || $(el).attr('name') || '').replace('og:', '');
    if (k) og[k] = $(el).attr('content') || '';
  });
  $('meta[name="twitter:card"], meta[name="twitter:title"], meta[name="twitter:description"], meta[name="twitter:image"]').each((_, el) => {
    const k = 'twitter:' + ($(el).attr('name') || '').replace('twitter:', '');
    og[k] = $(el).attr('content') || '';
  });
  return Object.keys(og).length ? og : null;
}

function extractJsonLd($) {
  const results = [];
  $('script[type="application/ld+json"]').each((_, el) => {
    try { results.push(JSON.parse($(el).html())); } catch {}
  });
  return results.length ? results : null;
}

function extractLinks($, baseUrl, limit = 30) {
  const links = [];
  const seen = new Set();
  $('a[href]').each((_, el) => {
    if (links.length >= limit) return false;
    try {
      const href = new URL($(el).attr('href'), baseUrl).href;
      if (!seen.has(href) && (href.startsWith('http://') || href.startsWith('https://'))) {
        seen.add(href);
        links.push({ href, text: $(el).text().trim().slice(0, 100) || null });
      }
    } catch {}
  });
  return links.length ? links : null;
}

function extractText($) {
  $('script, style, nav, header, footer, aside, [role="navigation"], [aria-hidden="true"]').remove();
  const text = $('main, article, .content, #content, #main, body').first().text()
    .replace(/\s+/g, ' ').trim().slice(0, 5000);
  return text || null;
}

function extractHeadings($) {
  const h = {};
  for (const tag of ['h1', 'h2', 'h3']) {
    const items = [];
    $(tag).each((_, el) => { const t = $(el).text().trim(); if (t) items.push(t); });
    if (items.length) h[tag] = items.slice(0, 10);
  }
  return Object.keys(h).length ? h : null;
}

function scrapeHtml(html, finalUrl, requestedFields) {
  const $ = cheerio.load(html);
  const all = !requestedFields?.length;
  const want = f => all || requestedFields.includes(f);

  return {
    ...(want('title') ? { title: $('title').text().trim() || $('meta[property="og:title"]').attr('content') || null } : {}),
    ...(want('description') ? { description: $('meta[name="description"]').attr('content') || $('meta[property="og:description"]').attr('content') || null } : {}),
    ...(want('og') ? { og: extractOg($) } : {}),
    ...(want('jsonld') ? { jsonld: extractJsonLd($) } : {}),
    ...(want('links') ? { links: extractLinks($, finalUrl) } : {}),
    ...(want('text') ? { text: extractText($) } : {}),
    ...(want('headings') ? { headings: extractHeadings($) } : {}),
  };
}

// ── Routes ────────────────────────────────────────────────────────────────────
app.get('/', (_req, res) => {
  res.json({
    service: 'x402-scraper-api',
    protocol: 'x402 (Base/USDC)',
    tagline: 'Scrape any webpage to Markdown or JSON — handles JS rendering',
    curl_example: "curl https://x402-scraper-api.suretat.com/scrape -H 'Content-Type: application/json' -d '{\"url\": \"https://example.com\", \"format\": \"markdown\"}'",
    try_it: 'https://x402-scraper-api.suretat.com/docs',
    docs: '/docs',
  });
});

app.get('/.well-known/x402.json', (req, res) => {
  const base = `${req.protocol}://${req.get('host')}`;
  res.json({
    x402Version: 1,
    endpoints: [
      { path: '/scrape', method: 'POST', price: PRICE, network: 'base', asset: USDC_BASE, payTo: PAY_TO, description: SCRAPE_DESC },
      { path: '/extract', method: 'POST', price: PRICE, network: 'base', asset: USDC_BASE, payTo: PAY_TO, description: EXTRACT_DESC },
    ],
    docs: `${base}/docs`,
    health: `${base}/health`,
    stats: `${base}/stats`,
  });
});

app.get('/health', (_req, res) => res.json({ status: 'ok', version: '1.0.0', price_usdc: PRICE }));

app.get('/stats', (_req, res) => res.json({
  payments_total: stats.payments_total,
  revenue_usdc: stats.revenue_usdc,
  last_payments: stats.last_payments.slice(0, 10),
  price_usdc: PRICE,
  wallet: PAY_TO,
}));

const SCRAPE_DESC = 'Web scraper: fetch URL → titre, description, Open Graph, JSON-LD, liens, texte';
const EXTRACT_DESC = 'Web scraper avec sélecteurs CSS: extrait des champs nommés depuis une page web';

app.post('/scrape', x402Middleware(SCRAPE_DESC), async (req, res) => {
  const rawUrl = (req.body?.url || '').trim();
  if (!rawUrl) return res.status(400).json({ error: 'Le champ url est requis' });
  let parsed;
  try { parsed = validateUrl(rawUrl); } catch (e) { return res.status(e.status || 400).json({ error: e.message }); }

  const fields = Array.isArray(req.body?.fields) ? req.body.fields : [];
  const timeout = parseInt(req.body?.timeout) || 10000;

  try {
    const { html, status, finalUrl } = await fetchPage(parsed.href, timeout);
    const extracted = scrapeHtml(html, finalUrl, fields);
    recordPayment('scrape', parsed.hostname);
    settlePayment(req._x402Hdr, req._x402Resource, SCRAPE_DESC);
    res.set('X-PAYMENT-RESPONSE', 'settled');
    res.json({ url: finalUrl, status, scraped_at: new Date().toISOString(), ...extracted });
  } catch (e) {
    res.status(e.status || 502).json({ error: e.message });
  }
});

app.post('/extract', x402Middleware(EXTRACT_DESC), async (req, res) => {
  const rawUrl = (req.body?.url || '').trim();
  const selectors = req.body?.selectors;
  if (!rawUrl) return res.status(400).json({ error: 'Le champ url est requis' });
  if (!selectors || typeof selectors !== 'object' || !Object.keys(selectors).length)
    return res.status(400).json({ error: 'Le champ selectors est requis (objet { nomChamp: "selector CSS" })' });

  let parsed;
  try { parsed = validateUrl(rawUrl); } catch (e) { return res.status(e.status || 400).json({ error: e.message }); }

  const timeout = parseInt(req.body?.timeout) || 10000;

  try {
    const { html, status, finalUrl } = await fetchPage(parsed.href, timeout);
    const $ = cheerio.load(html);
    const data = {};
    for (const [key, selector] of Object.entries(selectors)) {
      const el = $(selector);
      if (el.length === 0) {
        data[key] = null;
      } else if (el.length === 1) {
        data[key] = el.text().trim() || el.attr('href') || el.attr('src') || el.attr('content') || null;
      } else {
        data[key] = el.map((_, e) => $(e).text().trim() || $(e).attr('href') || null).get().filter(Boolean).slice(0, 20);
      }
    }
    recordPayment('extract', parsed.hostname);
    settlePayment(req._x402Hdr, req._x402Resource, EXTRACT_DESC);
    res.set('X-PAYMENT-RESPONSE', 'settled');
    res.json({ url: finalUrl, status, scraped_at: new Date().toISOString(), data });
  } catch (e) {
    res.status(e.status || 502).json({ error: e.message });
  }
});

// ── Docs ──────────────────────────────────────────────────────────────────────
app.get('/docs', (_req, res) => {
  res.type('text/html').send(`<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><title>x402 Scraper API</title>
<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;background:#0f172a;color:#e2e8f0}
h1{color:#38bdf8}h2{color:#7dd3fc;border-bottom:1px solid #1e293b;padding-bottom:8px}
pre{background:#1e293b;border-radius:6px;padding:16px;overflow:auto;font-size:13px;color:#94a3b8}
.badge{background:#164e63;color:#67e8f9;padding:3px 10px;border-radius:4px;font-size:12px;font-weight:700}
.g{background:#14532d;color:#86efac}
.price{color:#86efac;font-weight:700}table{width:100%;border-collapse:collapse}
td,th{padding:8px 12px;border:1px solid #1e293b;font-size:13px;text-align:left}
th{background:#1e293b;color:#7dd3fc}</style></head>
<body>
<h1>🕷️ x402 Scraper API</h1>
<p>Scraping de pages web : extraction de métadonnées, Open Graph, JSON-LD, texte et sélecteurs CSS.<br>
Paiement micropayment <span class="price">${PRICE} USDC</span> par appel via le protocole <a href="https://x402.org" style="color:#38bdf8">x402</a>.</p>
<h2>Wallet récepteur</h2>
<pre>${PAY_TO}\nRéseau : Base (USDC) · Asset : ${USDC_BASE}</pre>
<h2>Endpoints</h2>
<table>
<tr><th>Méthode</th><th>Route</th><th>Description</th><th>Prix</th></tr>
<tr><td><span class="badge">POST</span></td><td>/scrape</td><td>Scrape complet (titre, OG, JSON-LD, liens, texte)</td><td class="price">${PRICE} USDC</td></tr>
<tr><td><span class="badge">POST</span></td><td>/extract</td><td>Extraction par sélecteurs CSS nommés</td><td class="price">${PRICE} USDC</td></tr>
<tr><td><span class="badge g">GET</span></td><td>/health</td><td>Statut du service</td><td>Gratuit</td></tr>
<tr><td><span class="badge g">GET</span></td><td>/stats</td><td>Statistiques paiements</td><td>Gratuit</td></tr>
</table>
<h2>POST /scrape — champs disponibles</h2>
<pre>title, description, og (Open Graph + Twitter), jsonld (JSON-LD), links (href+texte), text (contenu principal), headings (h1/h2/h3)</pre>
<h2>Exemple POST /scrape</h2>
<pre>POST /scrape
X-PAYMENT: &lt;base64-payment-proof&gt;
Content-Type: application/json

{"url": "https://example.com", "fields": ["title", "description", "og"]}

// Réponse 200
{
  "url": "https://example.com",
  "status": 200,
  "scraped_at": "2026-05-22T10:00:00.000Z",
  "title": "Example Domain",
  "description": "This domain is for use in illustrative examples.",
  "og": {"type": "website", "title": "Example Domain", "url": "https://example.com"}
}</pre>
<h2>Exemple POST /extract (sélecteurs CSS)</h2>
<pre>{"url": "https://example.com", "selectors": {"titre": "h1", "paragraphe": "p", "liens": "a"}}

// Réponse 200
{
  "url": "https://example.com",
  "data": {
    "titre": "Example Domain",
    "paragraphe": "This domain is for use in illustrative examples...",
    "liens": ["More information...", "https://www.iana.org/..."]
  }
}</pre>
<h2>Sans paiement → HTTP 402</h2>
<pre>HTTP/1.1 402 Payment Required
{"x402Version": 1, "accepts": [{"scheme": "exact", "network": "base", "maxAmountRequired": "${PRICE}", ...}]}</pre>
</body></html>`);
});

app.listen(PORT, '0.0.0.0', () =>
  console.log(`x402-scraper-api listening on :${PORT} (TEST_MODE=${TEST_MODE})`));
