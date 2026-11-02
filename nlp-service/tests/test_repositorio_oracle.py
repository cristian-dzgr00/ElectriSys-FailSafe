"""El agente usa Oracle si responde y cae al CSV si no."""
from app.ner import agente_errores, repositorio_oracle


def _fila(error, correcto):
    return {"tipo": "marca", "error": error, "correcto": correcto, "nivel": "1", "origen": "auto", "nota": ""}


def test_sin_dsn_no_esta_disponible(monkeypatch):
    monkeypatch.delenv("ORACLE_NLP_DSN", raising=False)
    assert repositorio_oracle.leer() is None
    assert repositorio_oracle.guardar([], []) is False


def test_dsn_invalido_cae_a_none(monkeypatch):
    monkeypatch.setenv("ORACLE_NLP_DSN", "host-inexistente:1521/x")
    assert repositorio_oracle.leer() is None


def test_estado_usa_oracle_cuando_responde(monkeypatch):
    monkeypatch.setattr(repositorio_oracle, "leer", lambda: ([_fila("toyotta", "Toyota")], []))
    agente_errores._reiniciar_estado()
    try:
        assert list(agente_errores._cargar_estado()["filas"]) == ["toyotta"]
    finally:
        agente_errores._reiniciar_estado()


def test_estado_cae_al_csv_si_oracle_falla(monkeypatch):
    monkeypatch.setattr(repositorio_oracle, "leer", lambda: None)
    agente_errores._reiniciar_estado()
    try:
        assert len(agente_errores._cargar_estado()["filas"]) > 0
    finally:
        agente_errores._reiniciar_estado()
