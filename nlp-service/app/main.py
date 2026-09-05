"""ElectriSys - Microservicio de NLP para recomendación de repuestos.

Sprint 4: /nlp/consultar ya expone el pipeline completo — intención,
entidades, sugerencias rankeadas y la respuesta en lenguaje natural
generada por plantillas (sin LLM externo).
"""
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.intent.train import MODEL_PATH, entrenar
from app.pipeline import procesar_consulta

app = FastAPI(title="ElectriSys NLP Service", version="0.4.0")


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
    return procesar_consulta(payload.texto)
