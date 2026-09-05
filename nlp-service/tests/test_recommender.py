from app.recommender.tfidf_cosine import SimilitudTfidfCoseno


def test_rankear_lista_vacia_no_crashea():
    estrategia = SimilitudTfidfCoseno()
    assert estrategia.rankear("cualquier cosa", []) == []


def test_rankear_ordena_por_similitud():
    estrategia = SimilitudTfidfCoseno()
    candidatos = [
        {"nombre": "Bombillo LED 12W", "descripcion": "iluminacion led", "categoria": "Iluminacion"},
        {"nombre": "Filtro de aceite K&N HP-1002", "descripcion": "filtro de aceite alto flujo", "categoria": "Filtros"},
        {"nombre": "Filtro de aceite Mobil 1 M1-102", "descripcion": "filtro de aceite sintetico", "categoria": "Filtros"},
    ]
    resultado = estrategia.rankear(
        "no hay filtro de aceite original de toyota, que recomiendo", candidatos
    )
    assert resultado[0]["nombre"].startswith("Filtro")
    assert resultado[-1]["nombre"] == "Bombillo LED 12W"
    assert all("similitud" in c for c in resultado)
    assert resultado[0]["similitud"] >= resultado[-1]["similitud"]


def test_rankear_preserva_campos_originales():
    estrategia = SimilitudTfidfCoseno()
    candidatos = [{"nombre": "Filtro", "codigo": "ABC-1", "stock": 5}]
    resultado = estrategia.rankear("filtro", candidatos)
    assert resultado[0]["codigo"] == "ABC-1"
    assert resultado[0]["stock"] == 5


def test_rankear_sin_descripcion_no_crashea():
    estrategia = SimilitudTfidfCoseno()
    candidatos = [{"nombre": "Filtro"}, {"nombre": "Batería"}]
    resultado = estrategia.rankear("filtro de aceite", candidatos)
    assert len(resultado) == 2
