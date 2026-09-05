from app.preprocessing import normalizar, tokenizar, quitar_stopwords, preprocesar


def test_normalizar_minusculas():
    assert normalizar("HOLA Mundo") == "hola mundo"


def test_normalizar_quita_tildes():
    assert normalizar("aceite sintético") == "aceite sintetico"


def test_normalizar_quita_puntuacion():
    assert normalizar("¿Hay filtro de aceite?") == "hay filtro de aceite"


def test_normalizar_colapsa_espacios():
    assert normalizar("hola   mundo\n\tcomo estas") == "hola mundo como estas"


def test_normalizar_texto_vacio():
    assert normalizar("") == ""


def test_normalizar_preserva_negacion():
    # "no" distingue "recomendar_sustituto" ("no hay filtro") de
    # "buscar_repuesto" ("hay filtro"); no debe tratarse como stopword.
    tokens = tokenizar(normalizar("no hay filtro de aceite"))
    assert "no" in tokens


def test_quitar_stopwords_elimina_articulos_pero_preserva_negacion():
    tokens = tokenizar(normalizar("no hay el filtro de la Hilux"))
    resultado = quitar_stopwords(tokens)
    assert "el" not in resultado
    assert "de" not in resultado
    assert "la" not in resultado
    assert "no" in resultado
    assert "filtro" in resultado
    assert "hilux" in resultado


def test_preprocesar_pipeline_completo():
    resultado = preprocesar("¿No hay filtro de aceite para la Hilux 2.7?")
    assert "no" in resultado
    assert "filtro" in resultado
    assert "hilux" in resultado
    assert "de" not in resultado
    assert "la" not in resultado


def test_preprocesar_texto_vacio_o_solo_espacios():
    assert preprocesar("") == []
    assert preprocesar("   ") == []


def test_preprocesar_maneja_emoji_y_caracteres_especiales_sin_crashear():
    resultado = preprocesar("no hay filtro 😀 !!! ### para la Hilux")
    assert "filtro" in resultado
    assert "hilux" in resultado
