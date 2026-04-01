// api/rpc.js — Vercel Serverless Proxy → GenLayer studionet
//
// ROOT CAUSE FIX: The previous version used global fetch() which requires
// Node.js 18+. If Vercel ran an older runtime, the function would crash
// and Vercel would return an HTML error page. The frontend would then parse
// that HTML as JSON → "Unexpected token '<'" error.
//
// This version uses Node.js built-in `https` module — works on Node 12, 14,
// 16, 18, 20. No dependencies. Never returns HTML.

const https = require('https');

const UPSTREAM_HOST = 'studio.genlayer.com';
const UPSTREAM_PORT = 8443;
const UPSTREAM_PATH = '/api';
const TIMEOUT_MS    = 58000; // 58s — just under Vercel's 60s maxDuration

function forwardToStudionet(bodyString) {
  return new Promise(function(resolve, reject) {
    var options = {
      hostname: UPSTREAM_HOST,
      port:     UPSTREAM_PORT,
      path:     UPSTREAM_PATH,
      method:   'POST',
      headers: {
        'Content-Type':   'application/json',
        'Content-Length': Buffer.byteLength(bodyString, 'utf8'),
      },
    };

    var req = https.request(options, function(upstream) {
      var chunks = [];
      upstream.on('data', function(chunk) { chunks.push(chunk); });
      upstream.on('end',  function() {
        resolve(Buffer.concat(chunks).toString('utf8'));
      });
      upstream.on('error', reject);
    });

    req.on('error', reject);

    // Hard timeout — AI consensus calls can be slow but shouldn't hang forever
    req.setTimeout(TIMEOUT_MS, function() {
      req.destroy(new Error('Upstream timeout after ' + TIMEOUT_MS + 'ms'));
    });

    req.write(bodyString);
    req.end();
  });
}

module.exports = async function handler(req, res) {
  // ── CORS — allow all origins ────────────────────────────────────────
  res.setHeader('Access-Control-Allow-Origin',  '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Access-Control-Max-Age',       '86400');

  if (req.method === 'OPTIONS') return res.status(200).end();

  if (req.method !== 'POST') {
    // Always return JSON, never HTML
    return res.status(405).json({
      jsonrpc: '2.0', id: null,
      error: { code: -32000, message: 'Method not allowed' },
    });
  }

  // Re-stringify: Vercel auto-parses JSON bodies, we need the raw string
  var bodyString;
  try {
    bodyString = typeof req.body === 'string'
      ? req.body
      : JSON.stringify(req.body);
  } catch (e) {
    return res.status(400).json({
      jsonrpc: '2.0', id: null,
      error: { code: -32700, message: 'Parse error: invalid body' },
    });
  }

  // Log for Vercel Function Logs (helps debugging)
  try {
    var parsed = JSON.parse(bodyString);
    console.log('[rpc]', parsed.method || '?', '| id:', parsed.id || '?');
  } catch (_) {}

  try {
    var rawText = await forwardToStudionet(bodyString);

    // Forward raw text directly — never re-parse or re-wrap
    // This guarantees the browser gets exactly what studionet returned
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    return res.status(200).send(rawText);

  } catch (err) {
    console.error('[rpc] upstream error:', err.message);

    // Return a valid JSON-RPC error object — NEVER an HTML page
    return res.status(200).json({
      jsonrpc: '2.0',
      id:      null,
      error: {
        code:    -32603,
        message: 'Proxy upstream error: ' + err.message,
      },
    });
  }
};
