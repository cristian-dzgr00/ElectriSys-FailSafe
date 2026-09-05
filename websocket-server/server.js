// ============================================================
// websocket-server/server.js
// Servidor WebSocket para notificaciones en tiempo real.
//
// Flujo:
//   1. PHP (GestorVentas) hace POST /notify con el evento
//   2. Este servidor reenvía a todos los clientes conectados
//      que tengan un JWT válido para ese tipo de evento
// ============================================================
import { WebSocketServer, WebSocket } from 'ws';
import http from 'http';
import jwt from 'jsonwebtoken';

const PORT       = parseInt(process.env.WS_PORT    ?? '8080', 10);
const JWT_SECRET = process.env.JWT_SECRET          ?? 'electrisys_jwt_secret_2024_super_seguro';
const NOTIFY_KEY = process.env.WS_NOTIFY_KEY       ?? 'ws_internal_notify_key';

// ── Mapa de conexiones autenticadas ──────────────────────────
/** @type {Map<string, {ws: WebSocket, userId: number, role: string}>} */
const clients = new Map();

// ── Servidor HTTP (para recibir notificaciones desde PHP) ─────
const httpServer = http.createServer((req, res) => {
  if (req.method === 'POST' && req.url === '/notify') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      // Verificar clave interna
      const authHeader = req.headers['x-notify-key'];
      if (authHeader !== NOTIFY_KEY) {
        res.writeHead(403);
        res.end(JSON.stringify({ error: 'Unauthorized notify key' }));
        return;
      }

      let event;
      try {
        event = JSON.parse(body);
      } catch {
        res.writeHead(400);
        res.end(JSON.stringify({ error: 'Invalid JSON' }));
        return;
      }

      broadcast(event);
      res.writeHead(200);
      res.end(JSON.stringify({ sent: clients.size }));
    });
    return;
  }

  // Health check
  if (req.url === '/health') {
    res.writeHead(200);
    res.end(JSON.stringify({ status: 'ok', clients: clients.size }));
    return;
  }

  res.writeHead(404);
  res.end();
});

// ── Servidor WebSocket ────────────────────────────────────────
const wss = new WebSocketServer({ server: httpServer });

wss.on('connection', (ws, req) => {
  // Extraer JWT de query string: ws://server/?token=<JWT>
  const url    = new URL(req.url, 'http://localhost');
  const token  = url.searchParams.get('token');

  if (!token) {
    ws.close(4001, 'Token requerido');
    return;
  }

  let decoded;
  try {
    decoded = jwt.verify(token, JWT_SECRET);
  } catch (err) {
    ws.close(4002, 'Token inválido o expirado');
    return;
  }

  const clientId = `${decoded.sub}_${Date.now()}`;
  clients.set(clientId, { ws, userId: decoded.sub, role: decoded.role ?? 'vendedor' });

  console.log(`[WS] Cliente conectado: userId=${decoded.sub} role=${decoded.role} total=${clients.size}`);

  // Confirmar conexión al cliente
  ws.send(JSON.stringify({ type: 'connected', userId: decoded.sub }));

  ws.on('close', () => {
    clients.delete(clientId);
    console.log(`[WS] Cliente desconectado: userId=${decoded.sub} total=${clients.size}`);
  });

  ws.on('error', err => {
    console.error(`[WS] Error cliente ${clientId}:`, err.message);
    clients.delete(clientId);
  });

  // Mantener viva la conexión
  ws.on('pong', () => { ws.isAlive = true; });
});

// ── Broadcast a todos los clientes conectados ──────────────────
function broadcast(event) {
  const payload = JSON.stringify(event);
  let sent = 0;

  for (const [id, client] of clients) {
    if (client.ws.readyState === WebSocket.OPEN) {
      // Filtrar por rol si el evento lo especifica
      if (event.targetRoles && !event.targetRoles.includes(client.role)) {
        continue;
      }
      client.ws.send(payload);
      sent++;
    } else {
      clients.delete(id);  // limpiar conexiones muertas
    }
  }

  console.log(`[WS] Broadcast event="${event.type}" sent=${sent}/${clients.size}`);
}

// ── Heartbeat para detectar conexiones muertas ────────────────
setInterval(() => {
  for (const [id, client] of clients) {
    if (client.ws.isAlive === false) {
      client.ws.terminate();
      clients.delete(id);
      continue;
    }
    client.ws.isAlive = false;
    client.ws.ping();
  }
}, 30_000);

httpServer.listen(PORT, () => {
  console.log(`[ElectriSys WS] Servidor WebSocket escuchando en :${PORT}`);
  console.log(`[ElectriSys WS] Endpoint WS:   ws://localhost:${PORT}?token=<JWT>`);
  console.log(`[ElectriSys WS] Endpoint HTTP: http://localhost:${PORT}/notify`);
});
