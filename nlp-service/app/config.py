"""Configuración del microservicio vía variables de entorno."""
import os

from dotenv import load_dotenv

load_dotenv()

# URL del backend PHP para el diccionario dinámico del NER (Sprint 3) y el
# motor de recomendación (Sprint 4). En Sprint 5 se define con precisión
# cómo se alcanza desde dentro de docker-compose (backend-a solo habla
# FastCGI/PHP-FPM detrás de stunnel, no HTTP plano — probablemente haya que
# pasar por el contenedor "frontend"/nginx, o exponer un puerto interno
# dedicado). Por ahora, valor por defecto pensado para desarrollo local.
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")

# Clave interna backend -> microservicio (se usa desde la Sprint 5)
NLP_INTERNAL_KEY = os.getenv("NLP_INTERNAL_KEY", "")

# Token JWT para que el microservicio llame a rutas protegidas del backend
# (buscar-compatibles, etc.) mientras la Sprint 5 no defina el mecanismo
# definitivo de autenticación servicio-a-servicio. Se deja opcional: sin
# esto, esas llamadas devuelven 401 y el pipeline se degrada igual de
# controlado (ver client_backend.py y ner/dictionary.py, que la usan).
BACKEND_SERVICE_TOKEN = os.getenv("BACKEND_SERVICE_TOKEN", "")


def backend_auth_headers() -> dict:
    """Headers HTTP para llamar al backend. Centralizado acá para que
    client_backend.py y ner/dictionary.py no dupliquen esta lógica."""
    if BACKEND_SERVICE_TOKEN:
        return {"Authorization": f"Bearer {BACKEND_SERVICE_TOKEN}"}
    return {}
