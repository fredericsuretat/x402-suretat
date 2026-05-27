'use strict';
const express = require('express');
const cors    = require('cors');
const fs      = require('fs');
const path    = require('path');

const app  = express();
app.set('trust proxy', 1);
app.use(cors({ methods: ['GET', 'POST', 'OPTIONS'] }));
app.use(express.json());

const PORT        = parseInt(process.env.PORT || '3035');
const PAY_TO      = process.env.PAYMENT_ADDRESS || '0x6458941857a70C6cA18c440a316035A21901A12b';
const USDC_BASE   = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913';
const FACILITATOR = process.env.FACILITATOR_URL || 'https://x402.org/facilitator';
const PRICE       = process.env.PRICE_USDC || '0.001';
const DATA_FILE   = process.env.DATA_FILE || '/app/data/stats.json';
const TEST_MODE   = process.env.TEST_MODE === 'true';
const CDP_API_KEY_ID     = process.env.CDP_API_KEY_ID;
const CDP_API_KEY_SECRET = process.env.CDP_API_KEY_SECRET;

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
  '/geocode': {
    discoverable: true,
    category: 'geo',
    tags: ['geocoding', 'adresse', 'france', 'ban', 'coordinates', 'latitude', 'longitude'],
    bodyType: 'json',
    input: { q: '15 rue de la paix paris' },
    inputSchema: {
      type: 'object',
      properties: {
        q: { type: 'string', description: 'Adresse à géocoder (texte libre)' },
        limit: { type: 'number', description: 'Nombre de résultats max (1-5, défaut 1)' },
      },
      required: ['q'],
    },
    outputSchema: {
      type: 'object',
      properties: {
        label: { type: 'string' }, score: { type: 'number' },
        lat: { type: 'number' }, lon: { type: 'number' },
        type: { type: 'string' }, city: { type: 'string' },
        postcode: { type: 'string' }, street: { type: 'string' },
        housenumber: { type: 'string' }, context: { type: 'string' },
      },
    },
  },
  '/reverse': {
    discoverable: true,
    category: 'geo',
    tags: ['reverse-geocoding', 'adresse', 'france', 'ban', 'coordinates'],
    bodyType: 'json',
    input: { lat: 48.8534, lon: 2.3483 },
    inputSchema: {
      type: 'object',
      properties: {
        lat: { type: 'number', description: 'Latitude WGS84' },
        lon: { type: 'number', description: 'Longitude WGS84' },
      },
      required: ['lat', 'lon'],
    },
    outputSchema: {
      type: 'object',
      properties: {
        label: { type: 'string' }, distance: { type: 'number' },
        city: { type: 'string' }, postcode: { type: 'string' },
        street: { type: 'string' }, housenumber: { type: 'string' },
        lat: { type: 'number' }, lon: { type: 'number' },
      },
    },
  },
  '/commune': {
    discoverable: true,
    category: 'geo',
    tags: ['commune', 'france', 'insee', 'municipality', 'geo.api'],
    bodyType: 'json',
    input: { nom: 'Villefontaine' },
    inputSchema: {
      type: 'object',
      properties: {
        nom: { type: 'string', description: 'Nom de la commune (partiel accepté)' },
        code: { type: 'string', description: 'Code INSEE de la commune (5 chiffres)' },
        codePostal: { type: 'string', description: 'Code postal (5 chiffres)' },
      },
    },
    outputSchema: {
      type: 'object',
      properties: {
        code: { type: 'string' }, nom: { type: 'string' },
        codeDepartement: { type: 'string' }, codeRegion: { type: 'string' },
        population: { type: 'number' },
        centre: { type: 'object', properties: { coordinates: { type: 'array' } } },
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

// ── Geo APIs (data.gouv.fr) ───────────────────────────────────────────────────
const GEO_HEADERS = { 'User-Agent': 'x402-geocoder-fr/1.0 (contact: frederic@suretat.com)' };

async function banGeocode(q, limit = 1) {
  const url = `https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(q)}&limit=${Math.min(limit, 5)}`;
  const r = await fetch(url, { headers: GEO_HEADERS, signal: AbortSignal.timeout(8000) });
  if (!r.ok) throw Object.assign(new Error(`BAN API ${r.status}`), { status: 502 });
  const data = await r.json();
  if (!data.features?.length) throw Object.assign(new Error('Aucun résultat pour cette adresse'), { status: 404 });
  return data.features.map(f => ({
    label: f.properties.label,
    score: f.properties.score,
    lat: f.geometry.coordinates[1],
    lon: f.geometry.coordinates[0],
    type: f.properties.type,
    housenumber: f.properties.housenumber || null,
    street: f.properties.street || f.properties.name || null,
    postcode: f.properties.postcode,
    city: f.properties.city,
    context: f.properties.context,
    id: f.properties.id,
  }));
}

async function banReverse(lat, lon) {
  const url = `https://api-adresse.data.gouv.fr/reverse/?lat=${lat}&lon=${lon}`;
  const r = await fetch(url, { headers: GEO_HEADERS, signal: AbortSignal.timeout(8000) });
  if (!r.ok) throw Object.assign(new Error(`BAN API ${r.status}`), { status: 502 });
  const data = await r.json();
  if (!data.features?.length) throw Object.assign(new Error('Aucune adresse trouvée à ces coordonnées'), { status: 404 });
  const f = data.features[0];
  return {
    label: f.properties.label,
    distance: f.properties.distance,
    lat: f.geometry.coordinates[1],
    lon: f.geometry.coordinates[0],
    type: f.properties.type,
    housenumber: f.properties.housenumber || null,
    street: f.properties.street || f.properties.name || null,
    postcode: f.properties.postcode,
    city: f.properties.city,
    context: f.properties.context,
    id: f.properties.id,
  };
}

async function geoApiCommune({ nom, code, codePostal } = {}) {
  let url;
  if (code) {
    url = `https://geo.api.gouv.fr/communes/${encodeURIComponent(code)}?fields=code,nom,codeDepartement,codeRegion,population,centre,codesPostaux`;
  } else if (codePostal) {
    url = `https://geo.api.gouv.fr/communes?codePostal=${encodeURIComponent(codePostal)}&fields=code,nom,codeDepartement,codeRegion,population,centre,codesPostaux&limit=5`;
  } else if (nom) {
    url = `https://geo.api.gouv.fr/communes?nom=${encodeURIComponent(nom)}&fields=code,nom,codeDepartement,codeRegion,population,centre,codesPostaux&limit=5&boost=population`;
  } else {
    throw Object.assign(new Error('Fournir nom, code, ou codePostal'), { status: 400 });
  }
  const r = await fetch(url, { headers: GEO_HEADERS, signal: AbortSignal.timeout(8000) });
  if (!r.ok) throw Object.assign(new Error(`Geo API ${r.status}`), { status: 502 });
  const data = await r.json();
  if (!data) throw Object.assign(new Error('Commune introuvable'), { status: 404 });
  return Array.isArray(data) ? data : [data];
}

// ── Routes ────────────────────────────────────────────────────────────────────
app.get('/', (_req, res) => {
  res.json({
    service: 'x402-geocoder-fr',
    protocol: 'x402 (Base/USDC)',
    tagline: 'Geocode French addresses to GPS coordinates — or reverse geocode',
    curl_example: "curl https://x402-geocoder-fr.suretat.com/geocode -H 'Content-Type: application/json' -d '{\"adresse\": \"Tour Eiffel, Paris\"}'",
    try_it: 'https://x402-geocoder-fr.suretat.com/docs',
    docs: '/docs',
  });
});

app.get('/.well-known/x402.json', (req, res) => {
  const base = `${req.protocol}://${req.get('host')}`;
  res.json({
    x402Version: 1,
    endpoints: [
      { path: '/geocode', method: 'POST', price: PRICE, network: 'base', asset: USDC_BASE, payTo: PAY_TO, description: GEOCODE_DESC },
      { path: '/reverse', method: 'POST', price: PRICE, network: 'base', asset: USDC_BASE, payTo: PAY_TO, description: REVERSE_DESC },
      { path: '/commune', method: 'POST', price: PRICE, network: 'base', asset: USDC_BASE, payTo: PAY_TO, description: COMMUNE_DESC },
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

const GEOCODE_DESC = 'Géocodage adresse française → coordonnées GPS — BAN (Base Adresse Nationale)';
const REVERSE_DESC = 'Géocodage inverse : coordonnées GPS → adresse française — BAN';
const COMMUNE_DESC = 'Recherche commune française par nom, code INSEE ou code postal — geo.api.gouv.fr';

app.post('/geocode', x402Middleware(GEOCODE_DESC), async (req, res) => {
  const q = (req.body?.q || '').trim();
  if (!q) return res.status(400).json({ error: 'Le champ q (adresse) est requis' });
  const limit = Math.max(1, Math.min(parseInt(req.body?.limit) || 1, 5));
  try {
    const results = await banGeocode(q, limit);
    recordPayment('geocode', q.slice(0, 60));
    settlePayment(req._x402Hdr, req._x402Resource, GEOCODE_DESC);
    res.set('X-PAYMENT-RESPONSE', 'settled');
    res.json(limit === 1 ? results[0] : results);
  } catch (e) {
    res.status(e.status || 502).json({ error: e.message });
  }
});

app.post('/reverse', x402Middleware(REVERSE_DESC), async (req, res) => {
  const lat = parseFloat(req.body?.lat);
  const lon = parseFloat(req.body?.lon);
  if (isNaN(lat) || isNaN(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180)
    return res.status(400).json({ error: 'Coordonnées invalides (lat: -90→90, lon: -180→180)' });
  try {
    const result = await banReverse(lat, lon);
    recordPayment('reverse', `${lat},${lon}`);
    settlePayment(req._x402Hdr, req._x402Resource, REVERSE_DESC);
    res.set('X-PAYMENT-RESPONSE', 'settled');
    res.json(result);
  } catch (e) {
    res.status(e.status || 502).json({ error: e.message });
  }
});

app.post('/commune', x402Middleware(COMMUNE_DESC), async (req, res) => {
  const { nom, code, codePostal } = req.body || {};
  if (!nom && !code && !codePostal)
    return res.status(400).json({ error: 'Fournir au moins un paramètre: nom, code (INSEE), ou codePostal' });
  try {
    const results = await geoApiCommune({ nom, code, codePostal });
    recordPayment('commune', nom || code || codePostal);
    settlePayment(req._x402Hdr, req._x402Resource, COMMUNE_DESC);
    res.set('X-PAYMENT-RESPONSE', 'settled');
    res.json(results.length === 1 ? results[0] : results);
  } catch (e) {
    res.status(e.status || 502).json({ error: e.message });
  }
});

// ── Docs ──────────────────────────────────────────────────────────────────────
app.get('/docs', (_req, res) => {
  res.type('text/html').send(`<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><title>x402 Geocoder FR</title>
<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;background:#0f172a;color:#e2e8f0}
h1{color:#38bdf8}h2{color:#7dd3fc;border-bottom:1px solid #1e293b;padding-bottom:8px}
pre{background:#1e293b;border-radius:6px;padding:16px;overflow:auto;font-size:13px;color:#94a3b8}
.badge{background:#164e63;color:#67e8f9;padding:3px 10px;border-radius:4px;font-size:12px;font-weight:700}
.g{background:#14532d;color:#86efac}
.price{color:#86efac;font-weight:700}table{width:100%;border-collapse:collapse}
td,th{padding:8px 12px;border:1px solid #1e293b;font-size:13px;text-align:left}
th{background:#1e293b;color:#7dd3fc}</style></head>
<body>
<h1>📍 x402 Geocoder FR</h1>
<p>Géocodage d'adresses et communes françaises via les APIs officielles <strong>BAN</strong> et <strong>geo.api.gouv.fr</strong>.<br>
Paiement micropayment <span class="price">${PRICE} USDC</span> par appel via le protocole <a href="https://x402.org" style="color:#38bdf8">x402</a>.</p>
<h2>Wallet récepteur</h2>
<pre>${PAY_TO}\nRéseau : Base (USDC) · Asset : ${USDC_BASE}</pre>
<h2>Endpoints</h2>
<table>
<tr><th>Méthode</th><th>Route</th><th>Description</th><th>Prix</th></tr>
<tr><td><span class="badge">POST</span></td><td>/geocode</td><td>Adresse texte → coordonnées GPS</td><td class="price">${PRICE} USDC</td></tr>
<tr><td><span class="badge">POST</span></td><td>/reverse</td><td>Coordonnées GPS → adresse</td><td class="price">${PRICE} USDC</td></tr>
<tr><td><span class="badge">POST</span></td><td>/commune</td><td>Recherche commune (nom/INSEE/CP)</td><td class="price">${PRICE} USDC</td></tr>
<tr><td><span class="badge g">GET</span></td><td>/health</td><td>Statut du service</td><td>Gratuit</td></tr>
<tr><td><span class="badge g">GET</span></td><td>/stats</td><td>Statistiques paiements</td><td>Gratuit</td></tr>
</table>
<h2>Exemple POST /geocode</h2>
<pre>POST /geocode
X-PAYMENT: &lt;base64-payment-proof&gt;
Content-Type: application/json

{"q": "15 rue de la paix paris"}

// Réponse 200
{
  "label": "15 Rue de la Paix 75002 Paris",
  "score": 0.97,
  "lat": 48.8696,
  "lon": 2.3308,
  "type": "housenumber",
  "housenumber": "15",
  "street": "Rue de la Paix",
  "postcode": "75002",
  "city": "Paris",
  "context": "75, Paris, Île-de-France"
}</pre>
<h2>Exemple POST /reverse</h2>
<pre>{"lat": 48.8534, "lon": 2.3483}
// Retourne l'adresse la plus proche des coordonnées</pre>
<h2>Exemple POST /commune</h2>
<pre>{"nom": "Villefontaine"}   // par nom
{"code": "38548"}            // par code INSEE
{"codePostal": "38090"}      // par code postal</pre>
<h2>Sans paiement → HTTP 402</h2>
<pre>HTTP/1.1 402 Payment Required
{"x402Version": 1, "accepts": [{"scheme": "exact", "network": "base", "maxAmountRequired": "${PRICE}", ...}]}</pre>
</body></html>`);
});

app.listen(PORT, '0.0.0.0', () =>
  console.log(`x402-geocoder-fr listening on :${PORT} (TEST_MODE=${TEST_MODE})`));
