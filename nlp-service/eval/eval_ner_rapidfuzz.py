"""Evaluación del NER y de RapidFuzz (Aplicación de la IA - ElectriSys).

Mide, con "acierto / no acierto":
  1. NER campo por campo (marca, modelo, año, motor, combustible, código, categoría).
  2. RapidFuzz: qué tanto acierta cuando la frase está bien escrita y cuando
     el usuario comete errores de tipeo (0, 1 y 2 errores en la palabra).
  3. Que el NER no invente entidades cuando la frase no menciona ninguna.
  4. Efecto de los errores de tipeo sobre la intención (TF-IDF no usa RapidFuzz).

Datos: (a) frases reales (data/intents_dataset.csv + eval/holdout_intent.csv),
anotadas automáticamente por coincidencia exacta con el catálogo; (b) frases
generadas con entidades conocidas (la verdad se conoce por construcción).
Semillas fijas: el resultado es reproducible.

Uso (desde nlp-service/):  python -m eval.eval_ner_rapidfuzz
"""
import json, random, re
from pathlib import Path

import numpy as np
import pandas as pd

from app.ner.extractor import extraer_entidades
from app.preprocessing import normalizar
from eval.eval_ner import MARCAS, MODELOS, CATEGORIAS

BASE = Path(__file__).resolve().parent
OUT = BASE / "resultados_ner_rapidfuzz.json"
SEED = 2026
random.seed(SEED); np.random.seed(SEED)

PARES = {"Toyota": ["Hilux", "Corolla", "Fortuner"], "Chevrolet": ["Spark", "Spark GT", "Aveo"],
         "Mazda": ["3", "CX-5"], "Nissan": ["Sentra", "Frontier"], "Hyundai": ["Tucson", "Accent"],
         "Kia": ["Rio", "Sportage"], "Renault": ["Logan", "Duster"], "Ford": ["Escape", "Fiesta"],
         "Suzuki": ["Swift"]}
# (frase del usuario, categoría correcta, grupo)
#  directa: la palabra se parece al nombre de la categoría o hay sinónimo programado
#  significado: solo se relaciona por significado (sin parecido de letras)
CATS = [("filtro de aceite", "Filtros", "directa"), ("filtros de aire", "Filtros", "directa"),
        ("pastillas de freno", "Frenos", "directa"), ("discos de freno", "Frenos", "directa"),
        ("bateria", "Baterías", "directa"), ("baterias", "Baterías", "directa"),
        ("suspension delantera", "Suspensión", "directa"), ("caja de transmision", "Transmisión", "directa"),
        ("bujias", "Encendido", "directa"), ("correa de distribucion", "Correas y Bandas", "directa"),
        ("amortiguadores", "Suspensión", "significado"), ("kit de embrague", "Transmisión", "significado"),
        ("balatas", "Frenos", "significado"), ("rotula superior", "Suspensión", "significado")]
MOTORES = ["1.4", "1.6", "2.0", "2.7", "3.0", "1600cc", "1400cc", "150cc"]
COMBS = ["gasolina", "diesel", "hibrido", "gas"]
CODIGOS = ["HP-1002", "M1-102", "90915-YZZD4", "FG-FF5320", "AB-1234", "K2-9001", "FO-3011"]
INICIOS = ["necesito", "busco", "¿tienen", "¿hay", "quiero cotizar", "¿cuánto cuesta", "me hace falta", "pregunto por"]

def coincide(esp, obt):
    if esp is None: return obt is None
    if isinstance(esp, str) and isinstance(obt, str): return esp.strip().lower() == obt.strip().lower()
    return esp == obt

def extraer(texto):
    return extraer_entidades(texto, MARCAS, MODELOS, CATEGORIAS)

# ---------------------------------------------------------------- errores de tipeo
_VEC = {"a": "sq", "e": "wr", "i": "uo", "o": "ip", "u": "yi", "s": "ad", "n": "bm", "r": "et", "t": "ry", "l": "k", "c": "xv", "m": "n"}
OPS = ["borrar", "duplicar", "sustituir", "transponer"]
def un_error(p, rng, op=None):
    if len(p) < 2: return p
    op = op or rng.choice(OPS)
    i = rng.randrange(len(p))
    if op == "borrar": return p[:i] + p[i + 1:]
    if op == "transponer" and i < len(p) - 1: return p[:i] + p[i + 1] + p[i] + p[i + 2:]
    if op == "sustituir": return p[:i] + rng.choice(_VEC.get(p[i], "aeiou")) + p[i + 1:]
    return p[:i] + p[i] + p[i:]
def con_errores(palabra, k, rng, op=None):
    q = palabra
    for _ in range(k):
        q = un_error(q, rng, op)
    return q if q != palabra else un_error(palabra, rng, op)

# ---------------------------------------------------------------- frases generadas
def generar(n, rng):
    casos = []
    for _ in range(n):
        marca = rng.choice(list(PARES)); modelo = rng.choice(PARES[marca])
        cat, cat_ok, grupo = rng.choice(CATS)
        verdad, trozos = {}, [rng.choice(INICIOS), cat]
        verdad["categoria"] = cat_ok
        veh = [marca.lower(), modelo.lower()]
        verdad["marca"], verdad["modelo"] = marca, modelo
        if rng.random() < .6: a = rng.randint(2005, 2024); veh.append(str(a)); verdad["anio"] = a
        if rng.random() < .35: m = rng.choice(MOTORES); veh.append(m); verdad["motor"] = m
        if rng.random() < .3: c = rng.choice(COMBS); veh.append(c); verdad["combustible"] = c
        trozos += ["para", "un" if rng.random() < .4 else "", " ".join(veh)]
        if rng.random() < .25: k = rng.choice(CODIGOS); trozos.append(f"codigo {k}"); verdad["codigo"] = k
        texto = " ".join(t for t in trozos if t)
        casos.append({"texto": texto, "verdad": verdad, "grupo": grupo, "cat_palabra": cat})
    return casos

def ordenar_valor(campo, v): return v

def evaluar():
    rng = random.Random(SEED)
    res = {}
    # ---------- 1) NER campo por campo (frases generadas, cuando el campo SÍ está)
    casos = generar(400, rng)
    por_campo = {}
    fallos = []
    for c in casos:
        ent = extraer(c["texto"])
        for campo, esp in c["verdad"].items():
            ok = coincide(esp, ent.get(campo))
            d = por_campo.setdefault(campo, [0, 0]); d[0 if ok else 1] += 1
            if not ok: fallos.append({"texto": c["texto"], "campo": campo, "esperado": esp, "obtenido": ent.get(campo)})
    res["ner_por_campo"] = {k: {"acierto": v[0], "no_acierto": v[1]} for k, v in por_campo.items()}
    # categoría: por grupo
    g = {}
    for c in casos:
        ok = coincide(c["verdad"]["categoria"], extraer(c["texto"]).get("categoria"))
        d = g.setdefault(c["grupo"], [0, 0]); d[0 if ok else 1] += 1
    res["categoria_por_grupo"] = {k: {"acierto": v[0], "no_acierto": v[1]} for k, v in g.items()}

    # ---------- 2) frases reales: marca/modelo por coincidencia exacta
    reales = pd.concat([pd.read_csv(BASE.parent / "data" / "intents_dataset.csv"),
                        pd.read_csv(BASE / "holdout_intent.csv")]).drop_duplicates("texto").reset_index(drop=True)
    def exacto(vocab, tn, especial=None):
        hallados = []
        for v in vocab:
            vn = normalizar(v)
            if vn == "3":
                if re.search(r"\bmazda 3\b", tn): hallados.append(v)
            elif re.search(rf"\b{re.escape(vn)}\b", tn): hallados.append(v)
        if not hallados: return None
        return max(hallados, key=len)
    real, excluidas = [], []
    for t in reales.texto:
        tn = normalizar(t)
        n_mod = sum(1 for v in MODELOS if normalizar(v) != "3" and re.search(rf"\b{re.escape(normalizar(v))}\b", tn))
        if n_mod > 1 or "toyta" in tn:   # dos modelos a la vez, o ya trae un error de tipeo: verdad ambigua
            excluidas.append(t); continue
        real.append({"texto": t, "tn": tn, "marca": exacto(MARCAS, tn), "modelo": exacto(MODELOS, tn)})
    # 2a) limpias: cuando SÍ hay entidad y cuando NO la hay
    r = {"marca": {"con_entidad": [0, 0], "sin_entidad": [0, 0]}, "modelo": {"con_entidad": [0, 0], "sin_entidad": [0, 0]}}
    fallos_real = []
    for c in real:
        ent = extraer(c["texto"])
        for campo in ("marca", "modelo"):
            esp = c[campo]; ok = coincide(esp, ent.get(campo))
            r[campo]["con_entidad" if esp else "sin_entidad"][0 if ok else 1] += 1
            if not ok: fallos_real.append({"texto": c["texto"], "campo": campo, "esperado": esp, "obtenido": ent.get(campo)})
    res["reales_limpias"] = {c: {k: {"acierto": v[0], "no_acierto": v[1]} for k, v in d.items()} for c, d in r.items()}
    res["n_frases_reales"] = len(real); res["frases_reales_excluidas"] = excluidas

    # ---------- 3) RapidFuzz con errores de tipeo (0/1/2)
    def tipeo(texto_norm, entidad_norm, k, rng):
        palabras = entidad_norm.split()
        objetivo = max(palabras, key=len)
        nuevo = con_errores(objetivo, k, rng)
        return re.sub(rf"\b{re.escape(objetivo)}\b", nuevo, texto_norm, count=1), objetivo, nuevo
    rf = {c: {n: {"acierto": 0, "no_acierto": 0} for n in (0, 1, 2)} for c in ("marca", "modelo", "categoria")}
    corto = {n: {"acierto": 0, "no_acierto": 0} for n in ("corto", "largo")}
    ejemplos_rf = []
    for rep in range(3):
        rr = random.Random(SEED + rep)
        # marca y modelo sobre frases reales
        for c in real:
            for campo in ("marca", "modelo"):
                esp = c[campo]
                if not esp or normalizar(esp) == "3": continue
                for k in (0, 1, 2):
                    if k == 0 and rep > 0: continue
                    if k == 0: t = c["tn"]
                    else: t, ob, nv = tipeo(c["tn"], normalizar(esp), k, rr)
                    ent = extraer(t); ok = coincide(esp, ent.get(campo))
                    rf[campo][k]["acierto" if ok else "no_acierto"] += 1
                    if k == 1:
                        lg = "corto" if len(max(normalizar(esp).split(), key=len)) <= 4 else "largo"
                        corto[lg]["acierto" if ok else "no_acierto"] += 1
                    if k and not ok and len(ejemplos_rf) < 400: ejemplos_rf.append({"campo": campo, "errores": k, "texto": t, "esperado": esp, "obtenido": ent.get(campo)})
        # categoría sobre frases generadas (solo las de grupo "directa" cuya palabra base el sistema entiende)
        for c in generar(120, rr):
            if c["grupo"] != "directa": continue
            base = normalizar(c["texto"])
            palabra = max(normalizar(c["cat_palabra"]).split(), key=len)
            for k in (0, 1, 2):
                if k == 0 and rep > 0: continue
                if k == 0: t = base
                else: t = re.sub(rf"\b{re.escape(palabra)}\b", con_errores(palabra, k, rr), base, count=1)
                ok = coincide(c["verdad"]["categoria"], extraer(t).get("categoria"))
                rf["categoria"][k]["acierto" if ok else "no_acierto"] += 1
    res["rapidfuzz"] = rf; res["rapidfuzz_nombre_corto_vs_largo_1_error"] = corto
    res["ejemplos_fallos_rapidfuzz"] = ejemplos_rf[:40]


    # ---------- 3b) RapidFuzz por TIPO de error (1 error)
    tipos = {op: {"acierto": 0, "no_acierto": 0} for op in OPS}
    for c in real:
        for campo in ("marca", "modelo"):
            esp = c[campo]
            if not esp or normalizar(esp) == "3": continue
            obj = max(normalizar(esp).split(), key=len)
            for op in OPS:
                for rep in range(3):
                    rr = random.Random(SEED * 7 + rep)
                    nv = con_errores(obj, 1, rr, op)
                    t = re.sub(rf"\b{re.escape(obj)}\b", nv, c["tn"], count=1)
                    ok = coincide(esp, extraer(t).get(campo))
                    tipos[op]["acierto" if ok else "no_acierto"] += 1
    res["rapidfuzz_por_tipo_error"] = tipos

    # ---------- 3c) formatos alternativos (regex): ¿entiende otras formas de escribir lo mismo?
    ALT = [("motor", "hilux 2.7 gasolina", "2.7"), ("motor", "hilux 2,7 gasolina", "2.7"), ("motor", "hilux 2.7L", "2.7"),
           ("motor", "hilux 2.7 litros", "2.7"), ("motor", "logan 1,6", "1.6"), ("motor", "logan de 1600 cc", "1600cc"),
           ("motor", "logan 1600cc", "1600cc"), ("anio", "logan 2018", 2018), ("anio", "logan modelo 2018", 2018),
           ("anio", "logan del 18", 2018), ("anio", "logan 2018-2021", 2018), ("codigo", "el HP-1002", "HP-1002"),
           ("codigo", "el hp 1002", "HP-1002"), ("codigo", "el HP1002", "HP-1002"), ("codigo", "el 90915-YZZD4", "90915-YZZD4"),
           ("combustible", "logan diesel", "diesel"), ("combustible", "logan diésel", "diesel"), ("combustible", "logan a gasolina", "gasolina"),
           ("combustible", "logan a gas", "gas"), ("combustible", "logan acpm", "diesel")]
    alt = []
    for campo, txt, esp in ALT:
        obt = extraer(txt).get(campo); alt.append({"campo": campo, "texto": txt, "esperado": esp, "obtenido": obt, "acierto": coincide(esp, obt)})
    res["formatos_alternativos"] = alt

    # ---------- 4) intención con errores de tipeo (validación cruzada, sin fuga)
    from sklearn.model_selection import StratifiedKFold
    from app.intent.train import _construir_pipeline
    df = reales.copy()
    X, y = df.texto.values, df.intencion.values
    skf = StratifiedKFold(5, shuffle=True, random_state=42)
    def sucio(texto, k, rr):
        pal = texto.split(); idx = [i for i, p in enumerate(pal) if len(re.sub(r"\W", "", p)) >= 4]
        for i in rr.sample(idx, min(k, len(idx))):
            core = re.sub(r"\W", "", pal[i]); pal[i] = pal[i].replace(core, con_errores(core, 1, rr)) if core else pal[i]
        return " ".join(pal)
    it = {n: {"acierto": 0, "no_acierto": 0} for n in (0, 1, 2)}
    rr = random.Random(SEED)
    for tr, te in skf.split(X, y):
        m = _construir_pipeline().fit(X[tr], y[tr])
        for k in (0, 1, 2):
            xt = [t if k == 0 else sucio(t, k, rr) for t in X[te]]
            pr = m.predict(xt)
            ok = int((pr == y[te]).sum()); it[k]["acierto"] += ok; it[k]["no_acierto"] += len(te) - ok
    res["intencion_con_tipeo"] = it
    res["fallos_generadas"] = fallos[:60]; res["fallos_reales"] = fallos_real[:60]
    OUT.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return res

if __name__ == "__main__":
    r = evaluar()
    print(json.dumps({k: v for k, v in r.items() if not k.startswith(("fallos", "ejemplos"))}, indent=1, ensure_ascii=False))
