import jwt as pyjwt

from app import config


def test_backend_auth_headers_vacio_sin_token_ni_secreto(monkeypatch):
    monkeypatch.setattr(config, "BACKEND_SERVICE_TOKEN", "")
    monkeypatch.setattr(config, "JWT_SECRET", "")
    assert config.backend_auth_headers() == {}


def test_backend_auth_headers_prioriza_token_manual(monkeypatch):
    monkeypatch.setattr(config, "BACKEND_SERVICE_TOKEN", "token-manual")
    monkeypatch.setattr(config, "JWT_SECRET", "algun-secreto")
    assert config.backend_auth_headers() == {"Authorization": "Bearer token-manual"}


def test_backend_auth_headers_autogenera_token_con_jwt_secret(monkeypatch):
    monkeypatch.setattr(config, "BACKEND_SERVICE_TOKEN", "")
    monkeypatch.setattr(config, "JWT_SECRET", "mi-secreto-compartido")
    monkeypatch.setattr(config, "_token_generado", None)
    monkeypatch.setattr(config, "_token_generado_exp", 0.0)

    headers = config.backend_auth_headers()
    assert "Authorization" in headers

    token = headers["Authorization"].removeprefix("Bearer ")
    payload = pyjwt.decode(token, "mi-secreto-compartido", algorithms=["HS256"])
    assert payload["iss"] == "electrisys"
    assert payload["rol"] == "admin"
    assert payload["exp"] > payload["iat"]


def test_generar_token_servicio_reutiliza_cache(monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET", "otro-secreto")
    monkeypatch.setattr(config, "_token_generado", None)
    monkeypatch.setattr(config, "_token_generado_exp", 0.0)

    primero = config._generar_token_servicio()
    segundo = config._generar_token_servicio()
    assert primero == segundo  # mismo token mientras no expire


def test_generar_token_servicio_no_valido_con_secreto_distinto(monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET", "secreto-correcto")
    monkeypatch.setattr(config, "_token_generado", None)
    monkeypatch.setattr(config, "_token_generado_exp", 0.0)

    token = config._generar_token_servicio()
    try:
        pyjwt.decode(token, "secreto-incorrecto", algorithms=["HS256"])
        assert False, "no debería validar con un secreto distinto"
    except pyjwt.InvalidSignatureError:
        pass
