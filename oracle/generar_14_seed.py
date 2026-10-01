"""Genera oracle/14_seed_posibles_errores.sql desde la tabla del NER.

La fuente de verdad de las filas es el generador determinista de
nlp-service (data/errores/posibles_errores.csv); este script solo la
traduce a SQL para cargarla en Oracle. Volver a correrlo cuando cambie
el CSV:

    python oracle/generar_14_seed.py

Usa MERGE por lotes y no INSERT fila por fila: 58 mil INSERT sueltos
tardan minutos en sqlplus y fallan con ORA-00001 si el seed se corre dos
veces; el MERGE se puede volver a ejecutar sin duplicar nada.
"""
import csv
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CSV = RAIZ / "nlp-service" / "data" / "errores" / "posibles_errores.csv"
SALIDA = Path(__file__).resolve().parent / "14_seed_posibles_errores.sql"
LOTE = 250  # filas por MERGE: lejos del límite de sqlplus y del parser


def _texto(valor: str) -> str:
    return "'" + valor.replace("'", "''") + "'"


def main() -> None:
    with CSV.open(encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))

    lineas = [
        "-- ============================================================",
        "-- ElectriSys — Carga inicial de la tabla de posibles errores",
        "-- 14. Seed de posibles_errores (catálogo semilla)",
        "-- Ejecutar conectado como ELECTRISYS, después de 13_posibles_errores.sql.",
        "--",
        "-- GENERADO por oracle/generar_14_seed.py desde",
        "-- nlp-service/data/errores/posibles_errores.csv. No editar a mano.",
        f"-- {len(filas)} filas en lotes de {LOTE} (MERGE: re-ejecutable).",
        "-- Archivo en UTF-8: usar NLS_LANG=.AL32UTF8 (cargar_esquema.sh lo exporta).",
        "-- ============================================================",
        "SET DEFINE OFF;",
        "SET FEEDBACK OFF;",
        "",
    ]
    for inicio in range(0, len(filas), LOTE):
        lote = filas[inicio:inicio + LOTE]
        # Oracle no admite "USING (...) s (col1, col2...)": los nombres de
        # columna van como alias en el primer SELECT del UNION ALL.
        primera = "SELECT {} AS tipo, {} AS error, {} AS correcto, {} AS nivel, {} AS origen, {} AS nota FROM dual"
        resto = "SELECT {}, {}, {}, {}, {}, {} FROM dual"
        selects = "\n    UNION ALL ".join(
            (primera if i == 0 else resto).format(
                _texto(r["tipo"]), _texto(r["error"]), _texto(r["correcto"]),
                int(r["nivel"]), _texto(r["origen"]), _texto(r["nota"]),
            )
            for i, r in enumerate(lote)
        )
        lineas += [
            "MERGE INTO posibles_errores d",
            "USING (",
            f"    {selects}",
            ") s",
            "ON (d.tipo = s.tipo AND d.error = s.error)",
            "WHEN NOT MATCHED THEN INSERT (tipo, error, correcto, nivel, origen, nota)",
            "    VALUES (s.tipo, s.error, s.correcto, s.nivel, s.origen, s.nota);",
            "",
        ]
    lineas += [
        "COMMIT;",
        "SET FEEDBACK ON;",
        "SELECT tipo, COUNT(*) AS filas FROM posibles_errores GROUP BY tipo ORDER BY tipo;",
        "",
    ]
    SALIDA.write_text("\n".join(lineas), encoding="utf-8", newline="\n")
    print(f"{SALIDA.name}: {len(filas)} filas, {SALIDA.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
