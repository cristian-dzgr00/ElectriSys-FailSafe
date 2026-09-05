"""Configuración del microservicio vía variables de entorno."""
import os
import time

import jwt
from dotenv import load_dotenv

load_dotenv()

# URL del backend PHP (Sprint 3/4: diccionario dinámico del NER y motor de
# recomendación). El backend PHP no habla HTTP directo por sí mismo
# (php-fpm detrás de stunnel) — en docker-compose esto apunta al
# contenedor "frontend" (nginx), que proxya /api/ hacia el backend, igual
# que lo haría un navegador externo. Ver nginx/nginx.conf.
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")

# Clave que el backend PHP debe mandar en el header X-Internal-Key al
# llamar a /nlp/consultar — evita que cualquiera dentro de la red de
# Docker pueda usar el microservicio. Si queda vacía, no se exige (útil
# para desarrollo local fuera de Docker).
NLP_INTERNAL_KEY = os.getenv("NLP_INTERNAL_KEY", "")

# Mismo secreto que usa JwtMiddleware en el backend PHP (HS256). Permite
# que el microservicio firme su propio JWT de servicio para llamar a
# rutas protegidas del backend (buscar-compatibles, etc.) sin necesitar
# hacer login ni que un humano genere el token a mano.
JWT_SECRET = os.getenv("JWT_SECRET", "")

# Override manual opcional: si se define, se usa tal cual en vez de que
# el microservicio firme su propio token (útil para pruebas puntuales
# con un usuario real).
BACKEND_SERVICE_TOKEN = os.getenv("BACKEND_SERVICE_TOKEN", "")

_token_generado: str | None = None
_token_generado_exp: float = 0.0


def _generar_token_servicio() -> str:
    """Firma un JWT propio con el mismo secreto que el backend PHP.

    JwtMiddleware solo valida firma/expiración (no busca el `sub` contra
    la tabla usuarios para estas rutas), así que un token con datos de un
    "usuario de servicio" es válido sin necesitar login ni una fila real
    en la base de datos. Se cachea en memoria y se renueva antes de que
    expire.
    """
    global _token_generado, _token_generado_exp

    ahora = time.time()
    if _token_generado and ahora < _token_generado_exp - 60:
        return _token_generado

    exp = int(ahora) + 3600
    payload = {
        "iss": "electrisys",
        "iat": int(ahora),
        "exp": exp,
        "sub": 1,
        "nombre": "NLP Service",
        "email": "nlp-service@electrisys.internal",
        "rol": "admin",
    }
    _token_generado = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    _token_generado_exp = exp
    return _token_generado


def backend_auth_headers() -> dict:
    """Headers HTTP para llamar al backend PHP.

    Prioridad: BACKEND_SERVICE_TOKEN manual > token de servicio autofirmado
    (si hay JWT_SECRET) > sin autenticación (degradación ya controlada en
    client_backend.py / ner/dictionary.py, que solo tratan cualquier fallo
    como "backend no disponible").
    """
    token = BACKEND_SERVICE_TOKEN or (_generar_token_servicio() if JWT_SECRET else "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
