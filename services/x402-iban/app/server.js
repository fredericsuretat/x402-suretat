'use strict';
const express = require('express');
const cors    = require('cors');
const fs      = require('fs');
const path    = require('path');

const app = express();
app.set('trust proxy', 1);
app.use(cors({ methods: ['GET', 'POST', 'OPTIONS'] }));
app.use(express.json());

const PORT        = parseInt(process.env.PORT || '3032');
const PAY_TO      = process.env.PAYMENT_ADDRESS || '0x6458941857a70C6cA18c440a316035A21901A12b';
const USDC_BASE   = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913';
const FACILITATOR = process.env.FACILITATOR_URL || 'https://x402.org/facilitator';
const PRICE_DECIMAL = process.env.PRICE_USDC   || '0.0005';
const PRICE_ATOMIC  = process.env.PRICE_ATOMIC || String(Math.round(parseFloat(PRICE_DECIMAL) * 1_000_000));
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
const BAZAAR_VALIDATE = {
  discoverable: true,
  category: 'finance',
  tags: ['iban', 'validation', 'banking', 'finance', 'rib', 'europe'],
  bodyType: 'json',
  input: { iban: 'FR76 3000 6000 0112 3456 7890 189' },
  inputSchema: {
    type: 'object',
    properties: { iban: { type: 'string', description: 'Numéro IBAN (espaces autorisés, 50+ pays)' } },
    required: ['iban'],
  },
  outputSchema: {
    type: 'object',
    properties: {
      valid: { type: 'boolean' }, iban: { type: 'string' }, iban_formatted: { type: 'string' },
      country_code: { type: 'string' }, country_name: { type: 'string' },
      fr: { type: 'object', description: 'Décomposition RIB (France uniquement)' },
    },
  },
};

function buildRequirements(resource, description) {
  const pathname = new URL(resource).pathname;
  const bazaar = pathname === '/validate' ? BAZAAR_VALIDATE : undefined;
  return {
    scheme: 'exact', network: 'base', maxAmountRequired: PRICE_ATOMIC,
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

function recordPayment(country) {
  stats.payments_total++;
  stats.revenue_usdc = parseFloat((stats.revenue_usdc + parseFloat(PRICE_DECIMAL)).toFixed(8));
  stats.last_payments.unshift({ ts: new Date().toISOString(), country });
  if (stats.last_payments.length > 50) stats.last_payments.pop();
  saveStats();
}

// ── IBAN logic ────────────────────────────────────────────────────────────────

// Longueurs officielles IBAN par pays (ISO 13616)
const IBAN_LENGTHS = {
  AD:24,AE:23,AL:28,AT:20,AZ:28,BA:20,BE:16,BG:22,BH:22,BR:29,BY:28,
  CH:21,CR:22,CY:28,CZ:24,DE:22,DK:18,DO:28,EE:20,EG:29,ES:24,FI:18,
  FO:18,FR:27,GB:22,GE:22,GI:23,GL:18,GR:27,GT:28,HR:21,HU:28,IE:22,
  IL:23,IQ:23,IS:26,IT:27,JO:30,KW:30,KZ:20,LB:28,LC:32,LI:21,LT:20,
  LU:20,LV:21,LY:25,MC:27,MD:24,ME:22,MK:19,MR:27,MT:31,MU:30,NL:18,
  NO:15,PK:24,PL:28,PS:29,PT:25,QA:29,RO:24,RS:22,SA:24,SC:31,SE:24,
  SI:19,SK:24,SM:27,ST:25,SV:28,TL:23,TN:24,TR:26,UA:29,VA:22,VG:24,
  XK:20,
};

// Noms de pays
const COUNTRY_NAMES = {
  FR:'France',DE:'Allemagne',GB:'Royaume-Uni',BE:'Belgique',ES:'Espagne',
  IT:'Italie',NL:'Pays-Bas',CH:'Suisse',AT:'Autriche',PT:'Portugal',
  LU:'Luxembourg',MC:'Monaco',BE:'Belgique',PL:'Pologne',CZ:'Tchéquie',
  RO:'Roumanie',HU:'Hongrie',SK:'Slovaquie',HR:'Croatie',SI:'Slovénie',
  BG:'Bulgarie',EE:'Estonie',LT:'Lituanie',LV:'Lettonie',CY:'Chypre',
  MT:'Malte',GR:'Grèce',DK:'Danemark',SE:'Suède',FI:'Finlande',NO:'Norvège',
  IE:'Irlande',
};

function ibanChecksum(iban) {
  const rearranged = iban.slice(4) + iban.slice(0, 4);
  const numeric = rearranged.split('').map(c => {
    const code = c.charCodeAt(0);
    return code >= 65 && code <= 90 ? (code - 55).toString() : c;
  }).join('');
  // BigInt mod 97 sur la chaîne numérique
  let remainder = 0n;
  for (const ch of numeric) remainder = (remainder * 10n + BigInt(ch)) % 97n;
  return Number(remainder);
}

function parseIban(raw) {
  const iban = raw.toUpperCase().replace(/\s+/g, '');
  if (!/^[A-Z]{2}\d{2}[A-Z0-9]+$/.test(iban))
    return { valid: false, error: 'Format IBAN invalide' };

  const country = iban.slice(0, 2);
  const expectedLen = IBAN_LENGTHS[country];
  if (!expectedLen)
    return { valid: false, error: `Pays non reconnu : ${country}` };
  if (iban.length !== expectedLen)
    return { valid: false, error: `Longueur invalide pour ${country} : attendu ${expectedLen}, reçu ${iban.length}` };

  const checksum = ibanChecksum(iban);
  if (checksum !== 1)
    return { valid: false, error: `Checksum invalide (mod97=${checksum}, attendu 1)` };

  const result = {
    valid: true,
    iban,
    iban_formatted: iban.match(/.{1,4}/g).join(' '),
    country_code: country,
    country_name: COUNTRY_NAMES[country] || null,
    check_digits: iban.slice(2, 4),
    bban: iban.slice(4),
  };

  // Décomposition spécifique France (FR)
  if (country === 'FR') {
    const bban = iban.slice(4);
    result.fr = {
      code_banque:  bban.slice(0, 5),
      code_guichet: bban.slice(5, 10),
      numero_compte: bban.slice(10, 21),
      cle_rib:       bban.slice(21, 23),
    };
  }

  // Décomposition UK (GB)
  if (country === 'GB') {
    const bban = iban.slice(4);
    result.gb = {
      bank_code:    bban.slice(0, 4),
      sort_code:    bban.slice(4, 10),
      account_number: bban.slice(10),
    };
  }

  // Décomposition Belgique (BE)
  if (country === 'BE') {
    const bban = iban.slice(4);
    result.be = {
      bank_code:      bban.slice(0, 3),
      account_number: bban.slice(3, 9),
      check_digits:   bban.slice(9, 11),
    };
  }

  return result;
}

// ── Routes ────────────────────────────────────────────────────────────────────
app.get('/', (_req, res) => {
  res.json({
    service: 'x402-iban',
    protocol: 'x402 (Base/USDC)',
    tagline: 'Validate IBAN numbers — supports all EU countries, returns BIC and bank info',
    curl_example: "curl https://x402-iban.suretat.com/validate -H 'Content-Type: application/json' -d '{\"iban\": \"FR7630006000011234567890189\"}'",
    try_it: 'https://x402-iban.suretat.com/docs',
    docs: '/docs',
  });
});

app.get('/.well-known/x402', (req, res) => res.redirect('/.well-known/x402.json'));
app.get('/.well-known/x402.json', (req, res) => {
  const base = `${req.protocol}://${req.get('host')}`;
  res.json({
    x402Version: 1,
    endpoints: [
      { path: '/validate', method: 'POST', price: PRICE_DECIMAL, price_atomic: PRICE_ATOMIC, network: 'base', asset: USDC_BASE, payTo: PAY_TO, description: VALIDATE_DESC },
    ],
    docs: `${base}/docs`,
    health: `${base}/health`,
    stats: `${base}/stats`,
  });
});

app.get('/health', (_req, res) => res.json({ status: 'ok', version: '1.0.0', price_usdc: PRICE_DECIMAL, price_atomic: PRICE_ATOMIC }));

app.get('/stats', (_req, res) => res.json({
  payments_total: stats.payments_total,
  revenue_usdc: stats.revenue_usdc,
  last_payments: stats.last_payments.slice(0, 10),
  price_usdc: PRICE_DECIMAL,
  price_atomic: PRICE_ATOMIC,
  wallet: PAY_TO,
}));

const VALIDATE_DESC = 'Validation IBAN (checksum + structure) et décomposition RIB pour FR/GB/BE';

app.post('/validate', x402Middleware(VALIDATE_DESC), (req, res) => {
  const raw = req.body?.iban;
  if (!raw || typeof raw !== 'string')
    return res.status(400).json({ error: 'Champ "iban" requis' });
  if (raw.replace(/\s+/g, '').length > 40)
    return res.status(400).json({ error: 'IBAN trop long' });

  const result = parseIban(raw);
  if (result.valid) {
    recordPayment(result.country_code);
    settlePayment(req._x402Hdr, req._x402Resource, VALIDATE_DESC);
    res.set('X-PAYMENT-RESPONSE', 'settled');
  }
  res.json(result);
});

// ── Docs ──────────────────────────────────────────────────────────────────────
app.get('/docs', (_req, res) => {
  res.type('text/html').send(`<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><title>x402 IBAN Validator</title>
<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 20px;background:#0f172a;color:#e2e8f0}
h1{color:#38bdf8}h2{color:#7dd3fc;border-bottom:1px solid #1e293b;padding-bottom:8px}
pre{background:#1e293b;border-radius:6px;padding:16px;overflow:auto;font-size:13px;color:#94a3b8}
.badge{background:#164e63;color:#67e8f9;padding:3px 10px;border-radius:4px;font-size:12px;font-weight:700}
.g{background:#14532d;color:#86efac}
.price{color:#86efac;font-weight:700}table{width:100%;border-collapse:collapse}
td,th{padding:8px 12px;border:1px solid #1e293b;font-size:13px;text-align:left}
th{background:#1e293b;color:#7dd3fc}</style></head>
<body>
<h1>🏦 x402 IBAN Validator</h1>
<p>Validation de numéros IBAN (checksum ISO 13616) et décomposition structurée pour FR, GB, BE.<br>
Paiement micropayment <span class="price">${PRICE_DECIMAL} USDC</span> par appel via le protocole <a href="https://x402.org" style="color:#38bdf8">x402</a>.</p>
<h2>Wallet récepteur</h2>
<pre>${PAY_TO}\nRéseau : Base (USDC) · Asset : ${USDC_BASE}</pre>
<h2>Endpoints</h2>
<table>
<tr><th>Méthode</th><th>Route</th><th>Description</th><th>Prix</th></tr>
<tr><td><span class="badge">POST</span></td><td>/validate</td><td>Valide un IBAN, décompose RIB si FR/GB/BE</td><td class="price">${PRICE_DECIMAL} USDC</td></tr>
<tr><td><span class="badge g">GET</span></td><td>/health</td><td>Statut du service</td><td>Gratuit</td></tr>
<tr><td><span class="badge g">GET</span></td><td>/stats</td><td>Statistiques paiements</td><td>Gratuit</td></tr>
<tr><td><span class="badge g">GET</span></td><td>/docs</td><td>Cette page</td><td>Gratuit</td></tr>
</table>
<h2>Exemple POST /validate — IBAN français valide</h2>
<pre>POST /validate
X-PAYMENT: &lt;base64-payment-proof&gt;
Content-Type: application/json

{"iban": "FR76 3000 4008 0200 0100 1316 Z73"}

// Réponse 200 OK
{
  "valid": true,
  "iban": "FR7630004008020001001316Z73",
  "iban_formatted": "FR76 3000 4008 0200 0100 1316 Z73",
  "country_code": "FR",
  "country_name": "France",
  "check_digits": "76",
  "bban": "30004008020001001316Z73",
  "fr": {
    "code_banque":   "30004",
    "code_guichet":  "00802",
    "numero_compte": "00010013163",
    "cle_rib":       "73"
  }
}</pre>
<h2>IBAN invalide → HTTP 200 + valid: false</h2>
<pre>{"iban": "FR00 0000 0000 0000 0000 0000 000"}

// Réponse (le paiement N'EST PAS débité)
{
  "valid": false,
  "error": "Checksum invalide (mod97=47, attendu 1)"
}</pre>
<h2>Sans paiement → HTTP 402</h2>
<pre>HTTP/1.1 402 Payment Required
{
  "x402Version": 1,
  "accepts": [{ "scheme": "exact", "network": "base",
    "maxAmountRequired": "${PRICE_ATOMIC}", "payTo": "${PAY_TO}", "asset": "${USDC_BASE}" }],
  "error": "Payment required"
}</pre>
<h2>Pays supportés</h2>
<p>50+ pays selon la norme ISO 13616. Décomposition structurée disponible pour <strong>FR</strong>, <strong>GB</strong>, <strong>BE</strong>.</p>
</body></html>`);
});

app.listen(PORT, '0.0.0.0', () =>
  console.log(`x402-iban listening on :${PORT} (TEST_MODE=${TEST_MODE})`));
