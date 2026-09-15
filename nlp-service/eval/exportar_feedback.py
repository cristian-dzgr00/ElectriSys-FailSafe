"""Exporta feedback negativo de alta confianza para revisión humana.

Active learning con curación manual, no automático: junta las consultas
marcadas no-útiles (util=0) por el vendedor Y con confianza de intención
alta. Un feedback negativo con confianza baja ya era un caso dudoso para
el modelo (fallar ahí es esperable); uno con confianza alta es la señal
más interesante — el modelo estaba "seguro" y aun así la respuesta no
sirvió, lo que apunta a un hueco real en el dataset o una intención mal
aprendida.

El CSV de salida tiene EXACTAMENTE el mismo formato que
data/intents_dataset.csv (columnas texto,intencion) para poder pegarlo ahí
directo, pero SOLO después de que una persona revise cada fila — la
intención exportada es la que predijo el modelo (posiblemente la que hay
que corregir, no necesariamente la correcta). Este script NO reentrena ni
agrega nada al dataset por sí mismo.

Uso: python -m eval.exportar_feedback [--umbral-confianza 0.6] [--salida ruta.csv]

Requiere BACKEND_URL apuntando a un backend con datos, y
BACKEND_SERVICE_TOKEN con el JWT de un usuario con rol 'dueno'
(GET /api/asistente/consultas es solo para dueño, igual que /api/audit-log)
— el token de servicio que config.py autofirma para el resto del
microservicio es intencionalmente de rol 'vendedor' (mínimo privilegio,
ver app/config.py), así que NO alcanza para este script.
"""
import argparse
import csv
import json
from pathlib import Path

import httpx

from app.config import BACKEND_URL, backend_auth_headers

BASE_DIR = Path(__file__).resolve().parent
SALIDA_DEFAULT = BASE_DIR / "feedback_para_revision.csv"


def _obtener_consultas_no_utiles() -> list[dict]:
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(
            f"{BACKEND_URL}/api/asistente/consultas",
            params={"util": 0, "limit": 500},
            headers=backend_auth_headers(),
        )
        if resp.status_code == 403:
            raise SystemExit(
                "El backend respondió 403: BACKEND_SERVICE_TOKEN debe ser el JWT "
                "de un usuario con rol 'dueno' para leer /api/asistente/consultas."
            )
        resp.raise_for_status()
        return resp.json()["data"]


def exportar(umbral_confianza: float = 0.6, salida: Path = SALIDA_DEFAULT) -> int:
    filas = _obtener_consultas_no_utiles()
    seleccionadas = []
    for fila in filas:
        respuesta = json.loads(fila.get("respuesta_json") or "{}")
        confianza = respuesta.get("confianza", 0)
        if confianza >= umbral_confianza:
            seleccionadas.append((
                fila["texto_consulta"], fila.get("intencion_detectada") or "",
                fila["id"], confianza,
            ))

    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["texto", "intencion"])
        for texto, intencion, _id, _confianza in seleccionadas:
            writer.writerow([texto, intencion])

    for texto, intencion, id_, confianza in seleccionadas:
        print(f"  [consulta #{id_}, confianza={confianza:.2f}] \"{texto[:60]}\" -> {intencion}")

    return len(seleccionadas)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--umbral-confianza", type=float, default=0.6)
    parser.add_argument("--salida", type=Path, default=SALIDA_DEFAULT)
    args = parser.parse_args()

    n = exportar(args.umbral_confianza, args.salida)
    print(f"\n{n} filas exportadas a {args.salida} — revisar cada una a mano antes de sumarlas a data/intents_dataset.csv.")
