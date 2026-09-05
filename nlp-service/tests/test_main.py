from fastapi.testclient import TestClient

from app import config, main

client = TestClient(main.app)


def test_health_no_requiere_clave_interna(monkeypatch):
    monkeypatch.setattr(config, "NLP_INTERNAL_KEY", "clave-secreta")
    resp = client.get("/health")
    assert resp.status_code == 200


def test_consultar_sin_clave_interna_configurada_no_exige_nada(monkeypatch):
    monkeypatch.setattr(config, "NLP_INTERNAL_KEY", "")
    resp = client.post("/nlp/consultar", json={"texto": "hola"})
    assert resp.status_code == 200


def test_consultar_rechaza_sin_clave_interna_cuando_esta_configurada(monkeypatch):
    monkeypatch.setattr(config, "NLP_INTERNAL_KEY", "clave-secreta")
    resp = client.post("/nlp/consultar", json={"texto": "hola"})
    assert resp.status_code == 401


def test_consultar_rechaza_clave_interna_incorrecta(monkeypatch):
    monkeypatch.setattr(config, "NLP_INTERNAL_KEY", "clave-secreta")
    resp = client.post(
        "/nlp/consultar", json={"texto": "hola"}, headers={"X-Internal-Key": "otra-clave"}
    )
    assert resp.status_code == 401


def test_consultar_acepta_clave_interna_correcta(monkeypatch):
    monkeypatch.setattr(config, "NLP_INTERNAL_KEY", "clave-secreta")
    resp = client.post(
        "/nlp/consultar", json={"texto": "hola"}, headers={"X-Internal-Key": "clave-secreta"}
    )
    assert resp.status_code == 200
    assert resp.json()["intencion"] == "saludo_despedida"


def test_consultar_texto_vacio_sigue_dando_422(monkeypatch):
    monkeypatch.setattr(config, "NLP_INTERNAL_KEY", "")
    resp = client.post("/nlp/consultar", json={"texto": ""})
    assert resp.status_code == 422
