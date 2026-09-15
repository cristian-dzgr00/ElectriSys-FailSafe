from app.ner.extractor import (
    extraer_anio,
    extraer_combustible,
    extraer_entidades,
    extraer_motor,
)

MARCAS = ["Toyota", "Chevrolet", "Mazda", "Nissan", "Hyundai", "Kia", "Renault", "Ford", "Suzuki"]
MODELOS = [
    "Hilux", "Corolla", "Fortuner", "Spark", "Spark GT", "Aveo", "3", "CX-5",
    "Sentra", "Frontier", "Tucson", "Accent", "Rio", "Sportage", "Logan",
    "Duster", "Escape", "Fiesta", "Swift",
]
CATEGORIAS = [
    "Filtros", "Frenos", "Baterías", "Suspensión", "Motor", "Transmisión",
    "Encendido", "Correas y Bandas",
]


def test_extraer_anio_simple():
    assert extraer_anio("hilux 2.7 gasolina 2024") == 2024


def test_extraer_anio_ausente():
    assert extraer_anio("filtro de aceite para hilux") is None


def test_extraer_motor_formato_decimal():
    assert extraer_motor("hilux 2.7 gasolina 2024") == "2.7"


def test_extraer_motor_formato_cc():
    assert extraer_motor("motor de 1600cc") == "1600cc"


def test_extraer_motor_ausente():
    assert extraer_motor("filtro de aceite para hilux") is None


def test_extraer_combustible_variantes():
    assert extraer_combustible("hilux 2 7 gasolina 2024") == "gasolina"
    assert extraer_combustible("frontier diesel") == "diesel"
    assert extraer_combustible("motor diesel") == "diesel"  # ya sin tilde (texto normalizado)
    assert extraer_combustible("auto hibrido") == "hibrido"
    assert extraer_combustible("sin mencion de combustible") is None


def test_extraer_marca_con_typo():
    entidades = extraer_entidades("no hay filtro para una toyta hilux", marcas_conocidas=MARCAS)
    assert entidades["marca"] == "Toyota"


def test_extraer_marca_y_modelo_sin_typo():
    entidades = extraer_entidades(
        "filtro para chevrolet spark", marcas_conocidas=MARCAS, modelos_conocidos=MODELOS
    )
    assert entidades["marca"] == "Chevrolet"
    assert entidades["modelo"] == "Spark"


def test_extraer_marca_ausente_devuelve_none():
    entidades = extraer_entidades("necesito un filtro de aceite", marcas_conocidas=MARCAS)
    assert entidades["marca"] is None


def test_extraer_entidades_caso_completo_del_enunciado():
    texto = "No hay filtro de aceite original de Toyota para Hilux 2.7 gasolina 2024, que recomiendo"
    entidades = extraer_entidades(
        texto,
        marcas_conocidas=MARCAS,
        modelos_conocidos=MODELOS,
        categorias_conocidas=CATEGORIAS,
    )
    assert entidades["marca"] == "Toyota"
    assert entidades["modelo"] == "Hilux"
    assert entidades["anio"] == 2024
    assert entidades["motor"] == "2.7"
    assert entidades["combustible"] == "gasolina"


def test_extraer_entidades_sin_diccionarios_no_crashea():
    entidades = extraer_entidades("no hay filtro para hilux 2024")
    assert entidades["marca"] is None
    assert entidades["modelo"] is None
    assert entidades["anio"] == 2024


def test_extraer_entidades_texto_vacio_no_crashea():
    entidades = extraer_entidades("", marcas_conocidas=MARCAS)
    assert entidades["marca"] is None
    assert entidades["anio"] is None


def test_extraer_categoria_por_fuzzy():
    entidades = extraer_entidades("necesito un filtro de aceite", categorias_conocidas=CATEGORIAS)
    assert entidades["categoria"] == "Filtros"


def test_extraer_categoria_sinonimo_bujia():
    # Antes: "bujias" no matcheaba "Encendido" por fuzzy matching (ver evaluacion.md).
    entidades = extraer_entidades(
        "no hay bujias NGK para Kia Rio 2017", categorias_conocidas=CATEGORIAS
    )
    assert entidades["categoria"] == "Encendido"


def test_extraer_categoria_sinonimo_correa_distribucion():
    # Antes: "correa de distribucion" no matcheaba "Correas y Bandas"
    # (singular/plural + categoría de tres palabras, ver evaluacion.md).
    entidades = extraer_entidades(
        "no tengo en stock la correa de distribucion Gates para Sentra 2018",
        categorias_conocidas=CATEGORIAS,
    )
    assert entidades["categoria"] == "Correas y Bandas"


def test_extraer_categoria_sinonimo_ignora_si_no_esta_en_catalogo():
    # El sinónimo no debe inventar una categoría que no existe en el
    # catálogo real recibido como parámetro.
    entidades = extraer_entidades("no hay bujias", categorias_conocidas=["Filtros", "Frenos"])
    assert entidades["categoria"] is None
