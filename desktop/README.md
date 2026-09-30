# ElectriSys POS — cliente de escritorio

Aplicación de escritorio para Windows del punto de venta. Genera un `.exe`
instalable con icono propio, que abre el POS a pantalla completa sin barra
de direcciones.

## Qué es (y qué no es)

Es un **cliente**: se conecta al servidor de ElectriSys igual que lo haría
un navegador. **No** trae la base de datos ni el backend dentro.

Esa es una decisión de arquitectura, no una limitación:

- El POS es un sistema distribuido —un servidor, varias cajas—. Si cada
  `.exe` llevara su propia base, dos cajas venderían sobre inventarios
  distintos y el stock dejaría de significar nada.
- El inventario en tiempo real depende de que todas las cajas hablen con el
  mismo WebSocket. Empaquetar el servidor en cada caja rompería justamente
  la característica que el sistema tiene.
- Al no empaquetar el frontend, un cambio en una pantalla no obliga a
  reinstalar el `.exe` en cada caja: se actualiza el servidor y listo.

Lo que aporta frente a abrir el navegador: icono en la barra de tareas,
arranque directo al POS, el cajero no puede navegar a otro sitio, y una
pantalla de error propia que explica qué revisar cuando el servidor no
responde.

## Requisitos

- Node.js 18 o superior (para compilar; el `.exe` final no lo necesita).
- El servidor de ElectriSys corriendo y accesible.

## Uso en desarrollo

```bash
cd desktop
npm install
npm start
```

Abre la app apuntando a `http://localhost` (el nginx de `docker compose`).

## Generar el instalador

```bash
npm run dist
```

Deja en `desktop/dist/`:

| Archivo | Para qué |
|---|---|
| `ElectriSys POS Setup <versión>.exe` | Instalador: crea accesos directos y permite elegir carpeta |
| `ElectriSys POS <versión>.exe` | Portable: se ejecuta sin instalar, útil para la sustentación |

La primera compilación descarga los binarios de Electron (~100 MB) y tarda
unos minutos; las siguientes usan la caché.

## Configurar a qué servidor apunta

Por defecto: `http://localhost`.

Cada caja guarda su dirección en su propio perfil, así que se puede
cambiar sin recompilar:

```
%APPDATA%\electrisys-pos-desktop\config.json
```

```json
{ "servidor": "https://electrisys-pos.duckdns.org" }
```

Tres formas de cambiarla:

1. **Cuando falla la conexión**: la pantalla de error trae un campo para
   escribir la dirección y conectar.
2. **Menú → Archivo → Servidor…**: muestra la ruta del archivo y permite
   abrir su carpeta.
3. Editando el JSON a mano y reiniciando.

## Atajos

| Tecla | Acción |
|---|---|
| `F5` | Reconectar al servidor |
| `F11` | Pantalla completa |
| `F12` | Herramientas de desarrollo (útil para mostrar el WebSocket en vivo) |
| `Ctrl` + `+` / `-` / `0` | Zoom — para pantallas de caja pequeñas |

## Seguridad

La ventana carga una web remota, así que el renderer va aislado:
`contextIsolation` activo, `nodeIntegration` desactivado y `sandbox`
encendido. Lo único que el preload expone es cambiar la dirección del
servidor. Los enlaces externos se abren en el navegador del sistema, nunca
dentro de la ventana de la caja.
