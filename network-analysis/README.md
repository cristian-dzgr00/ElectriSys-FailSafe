# Análisis de tráfico — ElectriSys

Colección de scripts y perfiles para capturar y diseccionar
el tráfico real de ElectriSys en cada capa del modelo OSI.

## Requisitos

```bash
sudo apt install tcpdump wireshark tshark
```

## Scripts disponibles

| Script | Qué captura | Capa OSI |
|--------|------------|---------|
| `capture-login.sh` | Handshake TCP + JWT en headers HTTP | L4 + L7 |
| `capture-api.sh` | Peticiones REST completas a /api/* | L7 |
| `capture-mysql.sh` | Protocolo wire de MySQL | L7 |
| `capture-replication.sh` | Binlog replicación Primary→Replica | L7 |

## Uso rápido

```bash
# Capturar login y guardar en captures/
sudo ./scripts/capture-login.sh

# Abrir en Wireshark con el perfil de ElectriSys
wireshark -p -r captures/login_*.pcap
```

## Qué observar por tema

### TCP (Capa 4)
- Three-way handshake al login: `SYN → SYN-ACK → ACK`
- `RST` del servidor cuando el JWT es inválido
- Keep-alive entre Nginx y PHP-FPM

### HTTP/1.1 (Capa 7)
- Header `Authorization: Bearer <JWT>` — ver cómo viaja el token
- Response headers de seguridad: `X-Content-Type-Options`, `HSTS`
- Rate limit → respuesta `429 Too Many Requests`

### MySQL wire protocol (Capa 7)
- Handshake de autenticación MySQL
- Query packets: ver la consulta SQL en texto plano (antes de mTLS)
- Replication binlog: eventos `WRITE_ROWS`, `UPDATE_ROWS`

### Disector Lua personalizado
El archivo `wireshark-profile/electrisys.lua` agrega un disector
que resalta automáticamente los JWTs de ElectriSys en Wireshark.

```
Wireshark → Edit → Preferences → Protocols → ElectriSys JWT
```
