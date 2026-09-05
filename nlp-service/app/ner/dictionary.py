"""Diccionario dinámico de marcas/modelos/categorías para el NER.

Se alimenta de la base de datos real vía la API del backend (Sprint 1:
GET /api/vehiculos/marcas, /api/vehiculos/modelos, GET /api/categorias),
para que el NER reconozca lo que realmente existe en el catálogo en vez
de depender de una lista fija hardcodeada.

Si el backend no está disponible (todavía no hay integración de
autenticación entre servicios — eso llega en la Sprint 5) esto se degrada
a lista vacía o al último valor cacheado, en vez de tumbar el servicio:
año/motor/combustible se siguen extrayendo por regex de todas formas, solo
marca/modelo/categoría quedan sin reconocer.
"""
import logging
import time

import httpx

from app.config import BACKEND_URL, backend_auth_headers

logger = logging.getLogger(__name__)

_TTL_SEGUNDOS = 300  # 5 minutos
_TIMEOUT_SEGUNDOS = 3.0

_cache: dict[str, tuple[float, list[str]]] = {}


def _get_json(path: str) -> dict:
    with httpx.Client(timeout=_TIMEOUT_SEGUNDOS) as client:
        resp = client.get(f"{BACKEND_URL}{path}", headers=backend_auth_headers())
        resp.raise_for_status()
        return resp.json()


def _obtener_con_cache(clave: str, cargar_fn) -> list[str]:
    ahora = time.time()
    if clave in _cache:
        expira_en, valores = _cache[clave]
        if ahora < expira_en:
            return valores
    try:
        valores = cargar_fn()
        _cache[clave] = (ahora + _TTL_SEGUNDOS, valores)
        return valores
    except Exception as e:
        logger.warning("No se pudo refrescar '%s' desde el backend: %s", clave, e)
        if clave in _cache:
            return _cache[clave][1]  # mejor un valor viejo que nada
        return []


def obtener_marcas() -> list[str]:
    return _obtener_con_cache("marcas", lambda: _get_json("/api/vehiculos/marcas")["data"])


def obtener_modelos(marca: str | None = None) -> list[str]:
    if marca:
        clave = f"modelos:{marca.lower()}"
        return _obtener_con_cache(
            clave, lambda: _get_json(f"/api/vehiculos/modelos?marca={marca}")["data"]
        )

    def _todos_los_modelos() -> list[str]:
        vehiculos = _get_json("/api/vehiculos")["data"]
        return sorted({v["modelo"] for v in vehiculos})

    return _obtener_con_cache("modelos:*", _todos_los_modelos)


def obtener_categorias() -> list[str]:
    return _obtener_con_cache(
        "categorias", lambda: [c["nombre"] for c in _get_json("/api/categorias")["data"]]
    )


def invalidar_cache() -> None:
    _cache.clear()
