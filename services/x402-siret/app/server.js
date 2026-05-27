'use strict';
const express = require('express');
const cors    = require('cors');
const fs      = require('fs');
const path    = require('path');

const app  = express();
app.set('trust proxy', 1);
app.use(cors({ methods: ['GET', 'POST', 'OPTIONS'] }));
app.use(express.json());

const PORT        = parseInt(process.env.PORT || '3031');
const PAY_TO      = process.env.PAYMENT_ADDRESS || '0x6458941857a70C6cA18c440a316035A21901A12b';
const USDC_BASE   = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913';
const FACILITATOR = process.env.FACILITATOR_URL || 'https://x402.org/facilitator';
const PRICE       = process.env.PRICE_USDC || '0.003';
const DATA_FILE   = process.env.DATA_FILE || '/app/data/stats.json';
const TEST_MODE   = process.env.TEST_MODE === 'true';
const CDP_API_KEY_ID     = process.env.CDP_API_KEY_ID;
const CDP_API_KEY_SECRET = process.env.CDP_API_KEY_SECRET;

async function generateCdpJwt(method, path) {
  const { generateJwt } = require('@coinbase/cdp-sdk/auth');
  return generateJwt({ apiKeyId: CDP_API_KEY_ID, apiKeySecret: CDP_API_KEY_SECRET, requestMethod: method, requestHost: 'api.cdp.coinbase.com', requestPath: path, expiresIn: 120 });
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
  '/siret': {
    discoverable: true,
    category: 'data',
    tags: ['siret', 'siren', 'france', 'entreprise', 'insee', 'business'],
    bodyType: 'json',
    input: { siret: '55208131766522' },
    inputSchema: {
      type: 'object',
      properties: { siret: { type: 'string', description: 'Numéro SIRET (14 chiffres)' } },
      required: ['siret'],
    },
    outputSchema: {
      type: 'object',
      properties: {
        siret: { type: 'string' }, siren: { type: 'string' }, nom: { type: 'string' },
        ville: { type: 'string' }, activite_principale: { type: 'string' }, etat: { type: 'string' },
      },
    },
  },
  '/siren': {
    discoverable: true,
    category: 'data',
    tags: ['siret', 'siren', 'france', 'entreprise', 'insee', 'business'],
    bodyType: 'json',
    input: { siren: '552081317' },
    inputSchema: {
      type: 'object',
      properties: { siren: { type: 'string', description: 'Numéro SIREN (9 chiffres)' } },
      required: ['siren'],
    },
    outputSchema: {
      type: 'object',
      properties: {
        siren: { type: 'string' }, nom: { type: 'string' },
        siege: { type: 'object' }, nb_etablissements: { type: 'number' },
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

// ── INSEE API (recherche-entreprises.api.gouv.fr) ─────────────────────────────
const INSEE_HEADERS = { 'User-Agent': 'x402-siret/1.0 (contact: frederic@suretat.com)' };

async function searchEntreprise(q) {
  const url = `https://recherche-entreprises.api.gouv.fr/search?q=${encodeURIComponent(q)}&per_page=1`;
  const r = await fetch(url, { headers: INSEE_HEADERS, signal: AbortSignal.timeout(8000) });
  if (!r.ok) throw Object.assign(new Error(`INSEE ${r.status}`), { status: r.status >= 400 && r.status < 500 ? r.status : 502 });
  const data = await r.json();
  if (!data.results?.length) throw Object.assign(new Error('Aucun résultat pour ce numéro'), { status: 404 });
  return data.results[0];
}

function normalizeSiret(r, siret) {
  const siege = r.siege || {};
  return {
    siret: siege.siret || siret,
    siren: r.siren,
    nom: r.nom_raison_sociale || r.nom_complet,
    nom_complet: r.nom_complet,
    sigle: r.sigle || null,
    adresse: siege.adresse || null,
    code_postal: siege.code_postal || null,
    ville: siege.libelle_commune || null,
    coordonnees: siege.coordonnees || null,
    activite_principale: r.activite_principale || null,
    categorie: r.categorie_entreprise || null,
    etat: siege.etat_administratif || null,
    est_siege: siege.est_siege ?? null,
    date_creation: r.date_creation || null,
    nb_etablissements: r.nombre_etablissements || null,
    nb_etablissements_ouverts: r.nombre_etablissements_ouverts || null,
    dirigeants: (r.dirigeants || []).slice(0, 5).map(d => ({
      nom: d.nom, prenoms: d.prenoms, qualite: d.qualite, type: d.type_dirigeant,
    })),
  };
}

function normalizeSiren(r) {
  return {
    siren: r.siren,
    nom: r.nom_raison_sociale || r.nom_complet,
    nom_complet: r.nom_complet,
    sigle: r.sigle || null,
    siege: r.siege ? {
      siret: r.siege.siret,
      adresse: r.siege.adresse,
      code_postal: r.siege.code_postal,
      ville: r.siege.libelle_commune,
      coordonnees: r.siege.coordonnees || null,
    } : null,
    activite_principale: r.activite_principale || null,
    categorie: r.categorie_entreprise || null,
    date_creation: r.date_creation || null,
    nb_etablissements: r.nombre_etablissements || null,
    nb_etablissements_ouverts: r.nombre_etablissements_ouverts || null,
    dirigeants: (r.dirigeants || []).map(d => ({
      nom: d.nom, prenoms: d.prenoms, qualite: d.qualite, type: d.type_dirigeant,
    })),
  };
}

// ── Routes ────────────────────────────────────────────────────────────────────
app.get('/', (_req, res) => {
  res.json({
    service: 'x402-siret',
    protocol: 'x402 (Base/USDC)',
    tagline: 'Lookup French company by SIRET/SIREN — returns legal name, address, NAF code',
    curl_example: "curl https://x402-siret.suretat.com/siret -H 'Content-Type: application/json' -d '{\"siret\": \"44306184100047\"}'",
    try_it: 'https://x402-siret.suretat.com/docs',
    docs: '/docs',
  });
});

app.get('/.well-known/x402', (req, res) => res.redirect('/.well-known/x402.json'));
app.get('/.well-known/x402.json', (req, res) => {
  const base = `${req.protocol}://${req.get('host')}`;
  res.json({
    x402Version: 1,
    endpoints: [
      { path: '/siret', method: 'POST', price: PRICE, network: 'base', asset: USDC_BASE, payTo: PAY_TO, description: SIRET_DESC },
      { path: '/siren', method: 'POST', price: PRICE, network: 'base', asset: USDC_BASE, payTo: PAY_TO, description: SIREN_DESC },
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

const SIRET_DESC = 'Recherche établissement français par SIRET — Base SIRENE / data.gouv.fr';
const SIREN_DESC = 'Recherche entreprise française par SIREN + dirigeants — Base SIRENE / data.gouv.fr';

app.post('/siret', x402Middleware(SIRET_DESC), async (req, res) => {
  const siret = (req.body?.siret || '').replace(/[\s.]/g, '');
  if (!/^\d{14}$/.test(siret))
    return res.status(400).json({ error: 'SIRET invalide — 14 chiffres requis' });
  try {
    const raw = await searchEntreprise(siret);
    recordPayment('siret', siret.slice(0, 9) + '…');
    settlePayment(req._x402Hdr, req._x402Resource, SIRET_DESC);
    res.set('X-PAYMENT-RESPONSE', 'settled');
    res.json(normalizeSiret(raw, siret));
  } catch (e) {
    res.status(e.status || 502).json({ error: e.message });
  }
});

app.post('/siren', x402Middleware(SIREN_DESC), async (req, res) => {
  const siren = (req.body?.siren || '').replace(/[\s.]/g, '');
  if (!/^\d{9}$/.test(siren))
    return res.status(400).json({ error: 'SIREN invalide — 9 chiffres requis' });
  try {
    const raw = await searchEntreprise(siren);
    recordPayment('siren', siren);
    settlePayment(req._x402Hdr, req._x402Resource, SIREN_DESC);
    res.set('X-PAYMENT-RESPONSE', 'settled');
    res.json(normalizeSiren(raw));
  } catch (e) {
    res.status(e.status || 502).json({ error: e.message });
  }
});

// ── Docs ──────────────────────────────────────────────────────────────────────
app.get('/docs', (_req, res) => {
  res.type('text/html').send(`<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><title>x402 SIRET/SIREN API</title>
<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 20px;background:#0f172a;color:#e2e8f0}
h1{color:#38bdf8}h2{color:#7dd3fc;border-bottom:1px solid #1e293b;padding-bottom:8px}
pre{background:#1e293b;border-radius:6px;padding:16px;overflow:auto;font-size:13px;color:#94a3b8}
.badge{background:#164e63;color:#67e8f9;padding:3px 10px;border-radius:4px;font-size:12px;font-weight:700}
.g{background:#14532d;color:#86efac}
.price{color:#86efac;font-weight:700}table{width:100%;border-collapse:collapse}
td,th{padding:8px 12px;border:1px solid #1e293b;font-size:13px;text-align:left}
th{background:#1e293b;color:#7dd3fc}</style></head>
<body>
<h1>🏢 x402 SIRET / SIREN API</h1>
<p>Validation et enrichissement d'entreprises françaises via la base <strong>SIRENE officielle</strong> (data.gouv.fr).<br>
Paiement micropayment <span class="price">${PRICE} USDC</span> par appel via le protocole <a href="https://x402.org" style="color:#38bdf8">x402</a>.</p>
<h2>Wallet récepteur</h2>
<pre>${PAY_TO}\nRéseau : Base (USDC) · Asset : ${USDC_BASE}</pre>
<h2>Endpoints</h2>
<table>
<tr><th>Méthode</th><th>Route</th><th>Description</th><th>Prix</th></tr>
<tr><td><span class="badge">POST</span></td><td>/siret</td><td>Recherche par SIRET (14 chiffres)</td><td class="price">${PRICE} USDC</td></tr>
<tr><td><span class="badge">POST</span></td><td>/siren</td><td>Recherche par SIREN (9 chiffres) + dirigeants</td><td class="price">${PRICE} USDC</td></tr>
<tr><td><span class="badge g">GET</span></td><td>/health</td><td>Statut du service</td><td>Gratuit</td></tr>
<tr><td><span class="badge g">GET</span></td><td>/stats</td><td>Statistiques paiements</td><td>Gratuit</td></tr>
<tr><td><span class="badge g">GET</span></td><td>/docs</td><td>Cette page</td><td>Gratuit</td></tr>
</table>
<h2>Exemple POST /siret</h2>
<pre>POST /siret
X-PAYMENT: &lt;base64-payment-proof&gt;
Content-Type: application/json

{"siret": "55208131766522"}

// Réponse 200 OK
{
  "siret": "55208131766522",
  "siren": "552081317",
  "nom": "ELECTRICITE DE FRANCE",
  "sigle": "EDF",
  "adresse": "22-30 22 AVENUE DE WAGRAM 75008 PARIS",
  "code_postal": "75008",
  "ville": "PARIS",
  "activite_principale": "35.11Z",
  "categorie": "GE",
  "etat": "A",
  "dirigeants": [{"nom": "...", "qualite": "PDG", ...}]
}</pre>
<h2>Sans paiement → HTTP 402</h2>
<pre>HTTP/1.1 402 Payment Required
{
  "x402Version": 1,
  "accepts": [{
    "scheme": "exact", "network": "base",
    "maxAmountRequired": "${PRICE}",
    "payTo": "${PAY_TO}",
    "asset": "${USDC_BASE}"
  }],
  "error": "Payment required"
}</pre>
</body></html>`);
});

app.listen(PORT, '0.0.0.0', () =>
  console.log(`x402-siret listening on :${PORT} (TEST_MODE=${TEST_MODE})`));
