"""Genera oracle/19_posibles_errores_ampliados.sql a partir de los CSV del NLP.

La semilla original (14_seed_posibles_errores.sql) cargó 58.833 errores y 112 avisos.
Desde entonces el CSV creció (nlp-service/data/errores/); este script escribe un
SQL con SOLO las filas que la semilla no trae, de forma que Oracle y el archivo
vuelvan a coincidir sin borrar ni modificar nada.

Uso (desde la raíz del repo):
    python oracle/generar_19_posibles_errores_ampliados.py
"""
import csv
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SEMILLA = RAIZ / "oracle" / "14_seed_posibles_errores.sql"
CSV_ERRORES = RAIZ / "nlp-service" / "data" / "errores" / "posibles_errores.csv"
CSV_AVISOS = RAIZ / "nlp-service" / "data" / "errores" / "posibles_errores_avisos.csv"
SALIDA = RAIZ / "oracle" / "19_posibles_errores_ampliados.sql"
LOTE = 200  # filas por INSERT: mantiene cada sentencia corta para SQL*Plus

# VALUES (id,'tipo','error','correcto',nivel,'origen','nota')  — con '' como comilla escapada
_TXT = r"'((?:[^']|'')*)'"
RE_ERROR = re.compile(r"INTO posibles_errores \(id,tipo,error,correcto,nivel,origen,nota\) VALUES \(\d+," + _TXT + "," + _TXT + "," + _TXT + r",(\d)," + _TXT)
RE_AVISO = re.compile(r"INTO posibles_errores_avisos \(id,tipo,error,correcto,nivel,motivo\) VALUES \(\d+," + _TXT + "," + _TXT + "," + _TXT + r",(\d)," + _TXT)


def q(valor: str) -> str:
    return "'" + valor.replace("'", "''") + "'"


def main() -> None:
    semilla = SEMILLA.read_text(encoding="utf-8")
    ya_errores = {(t.replace("''", "'"), e.replace("''", "'"), c.replace("''", "'"))
                  for t, e, c, _n, _o in RE_ERROR.findall(semilla)}
    ya_avisos = {(t.replace("''", "'"), e.replace("''", "'"), c.replace("''", "'"))
                 for t, e, c, _n, _m in RE_AVISO.findall(semilla)}

    with CSV_ERRORES.open(encoding="utf-8", newline="") as f:
        nuevos = [r for r in csv.DictReader(f) if (r["tipo"], r["error"], r["correcto"]) not in ya_errores]
    with CSV_AVISOS.open(encoding="utf-8", newline="") as f:
        avisos = [r for r in csv.DictReader(f) if (r["tipo"], r["error"], r["correcto"]) not in ya_avisos]

    out = [
        "-- ============================================================",
        "-- ElectriSys — Ampliación de posibles_errores y posibles_errores_avisos",
        f"-- Agrega {len(nuevos)} errores de escritura y {len(avisos)} avisos que la semilla",
        "-- 14_seed_posibles_errores.sql no trae (están en nlp-service/data/errores/).",
        "--",
        "-- Ejecutar como ELECTRISYS, después de 14_seed_posibles_errores.sql.",
        "-- UTF-8: usar NLS_LANG=.AL32UTF8 al correr sqlplus.",
        "--",
        "-- Idempotente: los errores usan IGNORE_ROW_ON_DUPKEY_INDEX sobre la clave",
        "-- única (tipo, error, correcto) y los avisos llevan NOT EXISTS, así que",
        "-- puede correrse varias veces sin duplicar ni tocar lo que ya existe.",
        "-- Generado por oracle/generar_19_posibles_errores_ampliados.py",
        "-- ============================================================",
        "SET DEFINE OFF;",
        "SET SQLBLANKLINES ON;",
        "",
    ]
    for i in range(0, len(nuevos), LOTE):
        lote = nuevos[i:i + LOTE]
        selects = [
            f"SELECT {q(r['tipo'])},{q(r['error'])},{q(r['correcto'])},{int(r['nivel'])},{q(r['origen'])},{q(r['nota']) if r['nota'] else 'NULL'} FROM dual"
            for r in lote
        ]
        out.append("INSERT /*+ IGNORE_ROW_ON_DUPKEY_INDEX(posibles_errores(tipo,error,correcto)) */ INTO posibles_errores (tipo,error,correcto,nivel,origen,nota)")
        out.append("\nUNION ALL\n".join(selects) + ";")
        out.append("COMMIT;")
        out.append("")
    for r in avisos:
        out.append(
            "INSERT INTO posibles_errores_avisos (tipo,error,correcto,nivel,motivo) "
            f"SELECT {q(r['tipo'])},{q(r['error'])},{q(r['correcto'])},{int(r['nivel'])},{q(r['motivo'])} FROM dual "
            f"WHERE NOT EXISTS (SELECT 1 FROM posibles_errores_avisos x WHERE x.tipo = {q(r['tipo'])} "
            f"AND x.error = {q(r['error'])} AND x.correcto = {q(r['correcto'])});"
        )
    out += ["COMMIT;", "", "PROMPT Posibles errores y avisos ampliados.", ""]
    SALIDA.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"errores nuevos: {len(nuevos)} | avisos nuevos: {len(avisos)} | semilla: {len(ya_errores)} errores, {len(ya_avisos)} avisos")


if __name__ == "__main__":
    main()
