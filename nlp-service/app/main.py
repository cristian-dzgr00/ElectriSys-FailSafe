"""ElectriSys - Microservicio de NLP para recomendación de repuestos.

Sprint 3: /nlp/consultar ya clasifica intención y extrae entidades
(marca, modelo, año, motor, combustible, categoría). El motor de
recomendación y la generación de la respuesta final ("sugerencias",
"respuesta_texto") llegan en la Sprint 4.
"""
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.intent.classifier import predecir_intencion
from app.intent.train import MODEL_PATH, entrenar
from app.ner import dictionary
from app.ner.extractor import extraer_entidades
from app.preprocessing import normalizar, preprocesar

app = FastAPI(title="ElectriSys NLP Service", version="0.3.0")


@app.on_event("startup")
def _asegurar_modelo_entrenado():
    if not Path(MODEL_PATH).exists():
        entrenar()


class ConsultaRequest(BaseModel):
    texto: str = Field(..., min_length=1, max_length=1000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/nlp/consultar")
def consultar(payload: ConsultaRequest):
    intencion, confianza = predecir_intencion(payload.texto)
    entidades = extraer_entidades(
        payload.texto,
        marcas_conocidas=dictionary.obtener_marcas(),
        modelos_conocidos=dictionary.obtener_modelos(),
        categorias_conocidas=dictionary.obtener_categorias(),
    )
    return {
        "texto_original": payload.texto,
        "texto_normalizado": normalizar(payload.texto),
        "tokens": preprocesar(payload.texto),
        "intencion": intencion,
        "confianza": round(confianza, 4),
        "entidades": entidades,
    }
