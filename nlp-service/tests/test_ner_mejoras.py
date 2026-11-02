"""NER: marca inferida por modelo único, viscosidades y cilindradas que no son código ni modelo,
códigos reales, sinónimos de categoría y nombres cortos mal escritos."""
import pytest

from app.ner.extractor import (
    extraer_anio,
    extraer_codigo,
    extraer_combustible,
    extraer_entidades,
    extraer_motor,
)

MARCAS = ["Toyota", "Chevrolet", "Mazda", "Nissan", "Kia", "Renault", "Ford", "John Deere", "New Holland"]
MODELOS = ["Hilux", "Spark", "Spark GT", "3", "CX-5", "Sentra", "Rio", "Logan", "Escape", "5075E", "TL90", "Onix"]
CATEGORIAS = [
    "Filtros", "Frenos", "Baterías", "Suspensión", "Motor", "Transmisión", "Encendido",
    "Correas y Bandas", "Sistema Eléctrico", "Hidráulica", "Enganches y Acoples", "Neumáticos",
]
MARCA_DE_MODELO = {
    "Hilux": ["Toyota"], "Spark": ["Chevrolet"], "Spark GT": ["Chevrolet"], "3": ["Mazda"], "CX-5": ["Mazda"],
    "Sentra": ["Nissan"], "Rio": ["Kia"], "Logan": ["Renault"], "Escape": ["Ford"], "5075E": ["John Deere"],
    "TL90": ["New Holland"], "Onix": ["Chevrolet"],
}


def _e(texto, **kw):
    kw.setdefault("marca_de_modelo", MARCA_DE_MODELO)
    return extraer_entidades(texto, MARCAS, MODELOS, CATEGORIAS, **kw)


# ---------------------------------------------------------------- marca inferida
def test_modelo_unico_completa_la_marca():
    ent = _e("pastillas de freno para la hilux 2019")
    assert (ent["marca"], ent["modelo"], ent["anio"]) == ("Toyota", "Hilux", 2019)


def test_marca_escrita_gana_sobre_la_inferida():
    assert _e("bateria para toyota hilux")["marca"] == "Toyota"


def test_modelo_en_dos_marcas_deja_la_marca_sin_resolver():
    mapa = {**MARCA_DE_MODELO, "Rio": ["Kia", "Hyundai"]}
    assert _e("filtro para el rio", marca_de_modelo=mapa)["marca"] is None


def test_sin_tabla_modelo_a_marca_no_se_infiere_nada():
    assert extraer_entidades("filtro para hilux", MARCAS, MODELOS, CATEGORIAS)["marca"] is None


def test_la_tabla_modelo_a_marca_puede_ser_una_funcion_que_solo_se_llama_si_hace_falta():
    llamadas = []

    def mapa():
        llamadas.append(1)
        return MARCA_DE_MODELO

    assert _e("filtro para toyota hilux", marca_de_modelo=mapa)["marca"] == "Toyota"
    assert llamadas == []  # la marca ya estaba escrita
    assert _e("filtro para hilux", marca_de_modelo=mapa)["marca"] == "Toyota"
    assert llamadas == [1]


def test_mapa_vacio_no_rompe():
    assert _e("filtro para hilux", marca_de_modelo=lambda: {})["marca"] is None


# ---------------------------------------------------------------- cifras que no son código ni modelo
@pytest.mark.parametrize("texto", ["aceite 5W-30 para hilux", "aceite 10W40 para hilux", "aceite sae 15W-40 hilux", "0w-20 hilux"])
def test_viscosidad_no_es_codigo(texto):
    assert _e(texto)["codigo"] is None
    assert extraer_codigo(texto) is None


def test_viscosidad_da_la_categoria_motor():
    assert _e("necesito aceite 5W-30")["categoria"] == "Motor"


@pytest.mark.parametrize("texto,esperado", [
    ("filtro para hilux 3.2", "3.2"), ("bujias para hilux 2.7L", "2.7"), ("correa para spark 1,0", "1.0"),
    ("filtro para spark 1.6 litros", "1.6"), ("motor de 1400cc", "1400cc"),
])
def test_cilindrada_en_varios_formatos(texto, esperado):
    assert extraer_motor(texto) == esperado


@pytest.mark.parametrize("texto", ["tapa de radiador 1.1 bar", "disco de 3.5 mm", "llanta 18.4-46", "T6.120"])
def test_decimal_con_otra_unidad_no_es_cilindrada(texto):
    assert extraer_motor(texto) is None


def test_cilindrada_no_se_lee_como_el_modelo_3():
    ent = _e("filtro de aire para hilux 3.2")
    assert (ent["modelo"], ent["motor"]) == ("Hilux", "3.2")


@pytest.mark.parametrize("texto", ["necesito 3 filtros de aceite", "dame 3 bujias", "me quedan 3 baterias"])
def test_un_3_suelto_no_es_el_modelo_mazda_3(texto):
    ent = _e(texto)
    assert ent["modelo"] is None and ent["marca"] is None


@pytest.mark.parametrize("texto", ["bujias para mazda 3 2019", "bujias para mazda3 2019", "bujias para masda 3"])
def test_el_3_junto_a_mazda_si_es_el_modelo(texto):
    ent = _e(texto)
    assert ent["modelo"] == "3"
    assert ent["marca"] == "Mazda"


def test_el_3_del_codigo_no_es_modelo():
    ent = _e("cuanto vale el W-610/3")
    assert ent["modelo"] is None
    assert ent["codigo"] == "W-610/3"


# ---------------------------------------------------------------- códigos
@pytest.mark.parametrize("texto,esperado", [
    ("cuanto vale el HP-1002", "HP-1002"), ("el 90915-YZZD4 sirve", "90915-YZZD4"), ("tienes el KN-33-2304", "KN-33-2304"),
    ("el W-610/3 hay", "W-610/3"), ("M1-102 en stock", "M1-102"), ("filtro 26300-35505", "26300-35505"),
    ("el fg-ff5320", "FG-FF5320"),
])
def test_codigos_reales(texto, esperado):
    assert extraer_codigo(texto) == esperado


@pytest.mark.parametrize("texto", [
    "pastillas para swift 2015-2020", "bateria 12V-60Ah", "correa poly-V", "sistema start-stop", "llanta 205/55R16",
])
def test_no_son_codigos(texto):
    assert extraer_codigo(texto) is None


def test_un_modelo_con_guion_no_es_codigo():
    assert extraer_codigo("pastillas para cx-5", MODELOS) is None


# ---------------------------------------------------------------- año y combustible
def test_primer_anio_de_un_rango():
    assert extraer_anio("swift 2015-2020") == 2015


def test_un_precio_no_es_un_anio():
    assert extraer_anio("vale 2000 pesos") is None
    assert extraer_anio("vale $2000 el filtro") is None
    assert extraer_anio("hilux 2020, 2000 pesos") == 2020


def test_gas_solo_por_palabra_completa():
    assert extraer_combustible("carro a gas") == "gas"
    assert extraer_combustible("amortiguador a gas para fiesta") is None
    assert extraer_combustible("pago los gastos") is None


# ---------------------------------------------------------------- categorías
@pytest.mark.parametrize("texto,categoria", [
    ("balatas delanteras", "Frenos"), ("pastillas para el logan", "Frenos"), ("bandas de freno traseras", "Frenos"),
    ("acumulador para camioneta", "Baterías"), ("cauchos para el carro", "Neumáticos"), ("llanta 215/60R17", "Neumáticos"),
    ("amortiguadores traseros", "Suspensión"), ("terminal de direccion exterior", "Suspensión"),
    ("filtro de aire", "Filtros"), ("filtro hidraulico para tractor", "Hidráulica"),
    ("bobina de ignicion", "Encendido"), ("tensor de la banda", "Correas y Bandas"), ("banda del ventilador", "Correas y Bandas"),
    ("motor de arranque reconstruido", "Sistema Eléctrico"), ("alternador de 95 amperios", "Sistema Eléctrico"),
    ("kit de embrague completo", "Transmisión"), ("radiador de aluminio", "Motor"), ("pasador de enganche", "Enganches y Acoples"),
    ("rotula de enganche", "Enganches y Acoples"), ("aceite de transmision atf", "Transmisión"),
])
def test_sinonimos_de_categoria(texto, categoria):
    assert _e(texto)["categoria"] == categoria


def test_motor_del_vehiculo_no_es_la_categoria_motor():
    assert _e("motor de 1400cc para renault logan")["categoria"] is None
    assert _e("amortiguador para mazda 3 con motor 2.5")["categoria"] == "Suspensión"


def test_categoria_con_error_de_escritura_en_una_palabra_del_vocabulario():
    assert _e("vateria para kia rio")["categoria"] == "Baterías"


def test_sinonimo_de_categoria_ausente_del_catalogo_no_se_inventa():
    ent = extraer_entidades("balatas delanteras", categorias_conocidas=["Filtros", "Baterías"])
    assert ent["categoria"] is None


# ---------------------------------------------------------------- nombres con empate y nombres cortos
def test_spark_gt_gana_a_spark_cuando_el_texto_lo_dice():
    assert _e("chevrolet spark gt 2015 correa")["modelo"] == "Spark GT"
    assert _e("chevrolet spark 2015 correa")["modelo"] == "Spark"


@pytest.mark.parametrize("texto,campo,esperado", [
    ("bujias para qia rio", "marca", "Kia"),      # k/q suenan igual
    ("filtro para un kya", "marca", "Kia"),       # vocal interna por otra
    ("llantas para onyx", "modelo", "Onix"),      # i/y
    ("llantas para el onis", "modelo", "Onix"),   # x/s
])
def test_nombre_corto_con_error_de_oido(texto, campo, esperado):
    assert _e(texto)[campo] == esperado


def test_palabras_parecidas_a_un_nombre_corto_no_se_confunden():
    assert _e("el rin del carro")["modelo"] is None
    assert _e("pago en efectivo")["marca"] is None
    assert _e("dame el kiu")["marca"] is None  # vocal final distinta: ver tests/test_ner_errores.py


def test_palabra_distintiva_de_una_marca_de_varias_palabras():
    assert _e("repuestos para un holland tl90", marca_de_modelo=None)["marca"] == "New Holland"
