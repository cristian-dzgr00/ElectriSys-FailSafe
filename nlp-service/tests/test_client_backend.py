import pytest

from app import config
from app.recommender import client_backend


def test_buscar_compatibles_lanza_error_si_backend_no_disponible(monkeypatch):
    monkeypatch.setattr(client_backend, "BACKEND_URL", "http://localhost:1")
    with pytest.raises(client_backend.BackendNoDisponibleError):
        client_backend.buscar_compatibles("Toyota", "Hilux")


def test_buscar_en_catalogo_lanza_error_si_backend_no_disponible(monkeypatch):
    monkeypatch.setattr(client_backend, "BACKEND_URL", "http://localhost:1")
    with pytest.raises(client_backend.BackendNoDisponibleError):
        client_backend.buscar_en_catalogo("filtro")


def test_headers_incluye_bearer_si_hay_token(monkeypatch):
    monkeypatch.setattr(config, "BACKEND_SERVICE_TOKEN", "abc123")
    assert config.backend_auth_headers() == {"Authorization": "Bearer abc123"}


def test_headers_vacio_si_no_hay_token(monkeypatch):
    monkeypatch.setattr(config, "BACKEND_SERVICE_TOKEN", "")
    assert config.backend_auth_headers() == {}
