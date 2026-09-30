"""Grafica resultados_ner_rapidfuzz.json (acierto vs no acierto). Uso: python -m eval.graficar_ner_rapidfuzz [carpeta_salida]"""
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parent
R = json.loads((BASE / "resultados_ner_rapidfuzz.json").read_text(encoding="utf-8"))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "graficas"
OUT.mkdir(parents=True, exist_ok=True)
AZUL, NARANJA, TXT, GRIS = "#1B6FA8", "#E8890C", "#222222", "#5A5A5A"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": "#B8C4D0", "axes.labelcolor": TXT,
                     "xtick.color": TXT, "ytick.color": GRIS, "axes.spines.top": False, "axes.spines.right": False})

def pct(d): n = d["acierto"] + d["no_acierto"]; return 100 * d["acierto"] / n, 100 * d["no_acierto"] / n, n

def barras(ax, etiquetas, datos, titulo=None):
    w = 0.38
    for i, d in enumerate(datos):
        a, na, n = pct(d)
        ax.bar(i - w / 2, a, w - 0.04, color=AZUL, label="Acierto" if i == 0 else None)
        ax.bar(i + w / 2, na, w - 0.04, color=NARANJA, label="No acierto" if i == 0 else None)
        for x, v, k in ((i - w / 2, a, d["acierto"]), (i + w / 2, na, d["no_acierto"])):
            ax.text(x, v + 1.5, f"{v:.0f} %", ha="center", va="bottom", fontsize=10, color=TXT, fontweight="bold")
            if v < 88 and k > 0: ax.text(x, v + 9, f"({k})", ha="center", va="bottom", fontsize=8.5, color=GRIS)
    ax.set_xticks(range(len(etiquetas))); ax.set_xticklabels(etiquetas)
    ax.set_ylim(0, 118); ax.set_yticks([0, 25, 50, 75, 100]); ax.set_yticklabels([f"{t} %" for t in (0, 25, 50, 75, 100)])
    ax.yaxis.grid(True, color="#E3E9F0", linewidth=0.8); ax.set_axisbelow(True)
    if titulo: ax.set_title(titulo, fontsize=12, fontweight="bold", color=TXT, loc="left")

def guardar(fig, nombre, titulo, sub):
    fig.suptitle(titulo, x=0.06, ha="left", fontsize=15, fontweight="bold", color=TXT, y=0.99)
    fig.text(0.06, 0.925, sub, ha="left", fontsize=10, color=GRIS)
    fig.savefig(OUT / nombre, dpi=170, facecolor="white"); plt.close(fig)

# 1) NER por campo
c = R["ner_por_campo"]; g = R["categoria_por_grupo"]
campos = [("Marca", c["marca"]), ("Modelo", c["modelo"]), ("Año", c["anio"]), ("Motor", c["motor"]),
          ("Combustible", c["combustible"]), ("Código", c["codigo"]),
          ("Categoría\n(palabra\nparecida)", g["directa"]), ("Categoría\n(solo por\nsignificado)", g["significado"])]
fig, ax = plt.subplots(figsize=(12, 5.6)); fig.subplots_adjust(top=0.80, bottom=0.14, left=0.07, right=0.98)
barras(ax, [f"{n}\n(n={sum(d.values())})" for n, d in campos], [d for _, d in campos])
ax.legend(frameon=False, loc="upper right", ncol=2, bbox_to_anchor=(1, 1.13))
guardar(fig, "1_ner_acierto_por_campo.png", "NER: ¿acierta la entidad que pide el usuario?",
        "Frases generadas con entidad conocida (400). Se cuenta acierto cuando el valor extraído es exactamente el esperado.")

# 2) RapidFuzz por nivel de errores
rf = R["rapidfuzz"]; niv = ["Bien\nescrito", "1 error de\ntipeo", "2 errores de\ntipeo"]
fig, axs = plt.subplots(1, 3, figsize=(13, 5.4), sharey=True); fig.subplots_adjust(top=0.78, bottom=0.14, left=0.06, right=0.99, wspace=0.08)
for ax, campo, tit in zip(axs, ("marca", "modelo", "categoria"), ("Marca", "Modelo", "Categoría")):
    barras(ax, [f"{n}\n(n={sum(rf[campo][k].values())})" for n, k in zip(niv, ("0", "1", "2"))], [rf[campo][k] for k in ("0", "1", "2")], tit)
axs[0].legend(frameon=False, loc="upper left", ncol=2, bbox_to_anchor=(0, 1.16))
guardar(fig, "2_rapidfuzz_acierto_con_errores_de_tipeo.png", "RapidFuzz: ¿asocia bien las palabras mal escritas?",
        "Marca y modelo: frases reales del dataset. Categoría: frases generadas. El error se aplica a la palabra de la entidad (3 repeticiones).")

# 3) por tipo de error
t = R["rapidfuzz_por_tipo_error"]; nombres = {"borrar": "Falta una\nletra", "duplicar": "Letra\nrepetida", "sustituir": "Letra\ncambiada", "transponer": "Dos letras\nintercambiadas"}
fig, ax = plt.subplots(figsize=(11, 5.4)); fig.subplots_adjust(top=0.80, bottom=0.15, left=0.07, right=0.98)
barras(ax, [f"{nombres[k]}\n(n={sum(t[k].values())})" for k in ("duplicar", "borrar", "transponer", "sustituir")], [t[k] for k in ("duplicar", "borrar", "transponer", "sustituir")])
ax.legend(frameon=False, loc="upper right", ncol=2, bbox_to_anchor=(1, 1.13))
guardar(fig, "3_rapidfuzz_por_tipo_de_error.png", "RapidFuzz: acierto según el tipo de error de escritura",
        "Un solo error en el nombre de la marca o del modelo, dentro de frases reales del dataset.")

# 4) intención con errores de tipeo
it = R["intencion_con_tipeo"]
fig, ax = plt.subplots(figsize=(9, 5.4)); fig.subplots_adjust(top=0.80, bottom=0.15, left=0.09, right=0.98)
barras(ax, [f"{n}\n(n={sum(it[k].values())})" for n, k in zip(("Sin errores", "1 palabra\ncon error", "2 palabras\ncon error"), ("0", "1", "2"))], [it[k] for k in ("0", "1", "2")])
ax.legend(frameon=False, loc="upper right", ncol=2, bbox_to_anchor=(1, 1.13))
guardar(fig, "4_intencion_con_errores_de_tipeo.png", "Clasificador de intención: efecto de los errores de tipeo",
        "Validación cruzada de 5 partes sobre 401 frases; los errores se aplican solo a las frases de prueba de cada parte.")
print("listo", OUT)
