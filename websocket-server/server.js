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

const PORT       = parseInt(process.env.WS_PORT ?? '8080', 10);
const JWT_SECRET = process.env.JWT_SECRET;
const NOTIFY_KEY = process.env.WS_NOTIFY_KEY;

// Sin valores por defecto: antes había secretos reales escritos aquí como
// fallback, así que un despliegue al que se le olvidara definir las
// variables arrancaba igual con claves publicadas en el repositorio
// (cualquiera podía firmar JWTs válidos). Mejor fallar ruidosamente.
if (!JWT_SECRET || !NOTIFY_KEY) {
  console.error(
    '[ElectriSys WS] ERROR: faltan JWT_SECRET y/o WS_NOTIFY_KEY. ' +
    'Defínelas como variables de entorno antes de arrancar el servidor.'
  );
  process.exit(1);
}

// Tope del cuerpo aceptado en /notify. Los eventos son objetos JSON chicos.
const MAX_NOTIFY_BODY_BYTES = 64 * 1024;

// ── Mapa de conexiones autenticadas ──────────────────────────
/** @type {Map<string, {ws: WebSocket, userId: number, role: string}>} */
const clients = new Map();

// ── Servidor HTTP (para recibir notificaciones desde PHP) ─────
const httpServer = http.createServer((req, res) => {
  if (req.method === 'POST' && req.url === '/notify') {
    // Verificar la clave ANTES de leer el cuerpo: antes se acumulaba el
    // body completo y recién en 'end' se validaba, así que alguien sin
    // credenciales podía transmitir datos sin límite y agotar la memoria.
    if (req.headers['x-notify-key'] !== NOTIFY_KEY) {
      res.writeHead(403);
      res.end(JSON.stringify({ error: 'Unauthorized notify key' }));
      req.destroy();
      return;
    }

    let body = '';
    let recibidos = 0;
    let abortado = false;

    req.on('data', chunk => {
      if (abortado) return;
      recibidos += chunk.length;
      if (recibidos > MAX_NOTIFY_BODY_BYTES) {
        abortado = true;
        res.writeHead(413);
        res.end(JSON.stringify({ error: 'Payload too large' }));
        req.destroy();
        return;
      }
      body += chunk;
    });

    req.on('end', () => {
      if (abortado) return;

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
// El cliente ofrece los subprotocolos ['bearer', <JWT>]; aceptamos 'bearer'
// (hay que devolver uno que el cliente haya ofrecido o el navegador corta
// el handshake). El token ya NO viaja en la query string, que quedaba
// escrita en los access logs de nginx.
const wss = new WebSocketServer({
  server: httpServer,
  handleProtocols: protocols => (protocols.has('bearer') ? 'bearer' : false),
});

wss.on('connection', (ws, req) => {
  // Sec-WebSocket-Protocol llega como "bearer, <JWT>"
  const protocolos = (req.headers['sec-websocket-protocol'] ?? '')
    .split(',')
    .map(p => p.trim());
  const token = protocolos[0] === 'bearer' ? protocolos[1] : null;

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

  // El backend PHP emite el claim como "rol" (español), no "role":
  // leer decoded.role daba siempre undefined -> todos los clientes
  // quedaban como 'vendedor' y el filtro targetRoles no acertaba nunca,
  // así que ninguna notificación llegaba a nadie.
  const rol = decoded.rol ?? 'vendedor';
  const clientId = `${decoded.sub}_${Date.now()}`;
  clients.set(clientId, { ws, userId: decoded.sub, role: rol });

  console.log(`[WS] Cliente conectado: userId=${decoded.sub} rol=${rol} total=${clients.size}`);

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
  console.log(`[ElectriSys WS] Endpoint WS:   ws://localhost:${PORT} (subprotocolos: "bearer", <JWT>)`);
  console.log(`[ElectriSys WS] Endpoint HTTP: http://localhost:${PORT}/notify`);
});
