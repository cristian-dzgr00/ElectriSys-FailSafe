"""Cliente HTTP hacia el backend PHP para obtener candidatos de sustitución.

Usa las rutas construidas en la Sprint 1: buscar-compatibles, /repuestos
(búsqueda general) y /repuestos/{id}/compatibilidad. La Sprint 5 definirá
el mecanismo permanente de autenticación servicio-a-servicio y la ruta de
red dentro de docker-compose; mientras tanto, si BACKEND_SERVICE_TOKEN está
configurado se manda como Bearer (permite probar el flujo real hoy mismo).

Si el backend no responde, no autoriza, o devuelve error, estas funciones
lanzan BackendNoDisponibleError en vez de propagar la excepción cruda —
el pipeline la captura y responde con un mensaje de fallback controlado
en vez de un 500.
"""
import logging

import httpx

from app.config import BACKEND_URL, backend_auth_headers

logger = logging.getLogger(__name__)

_TIMEOUT_SEGUNDOS = 5.0


class BackendNoDisponibleError(Exception):
    """El backend no respondió, no autorizó, o devolvió un error."""


def _get(path: str, params: dict | None = None) -> dict:
    try:
        with httpx.Client(timeout=_TIMEOUT_SEGUNDOS) as client:
            resp = client.get(f"{BACKEND_URL}{path}", params=params, headers=backend_auth_headers())
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("Fallo al consultar %s en el backend: %s", path, e)
        raise BackendNoDisponibleError(str(e)) from e


def buscar_compatibles(
    marca: str,
    modelo: str,
    anio: int | None = None,
    motor: str | None = None,
    combustible: str | None = None,
    categoria: str | None = None,
) -> list[dict]:
    params = {"marca": marca, "modelo": modelo}
    if anio:
        params["anio"] = anio
    if motor:
        params["motor"] = motor
    if combustible:
        params["combustible"] = combustible
    if categoria:
        params["categoria"] = categoria
    return _get("/api/repuestos/buscar-compatibles", params).get("data", [])


def buscar_en_catalogo(termino: str, limit: int = 20) -> list[dict]:
    """Búsqueda general por nombre/código/categoría, sin filtrar por vehículo.

    Se usa como fallback cuando no hay compatibilidad exacta registrada, y
    como base de consultar_stock/consultar_precio/consultar_compatibilidad.
    """
    return _get("/api/repuestos", {"q": termino, "limit": limit}).get("data", [])


def obtener_compatibilidad(repuesto_id) -> list[dict]:
    return _get(f"/api/repuestos/{repuesto_id}/compatibilidad").get("data", [])
