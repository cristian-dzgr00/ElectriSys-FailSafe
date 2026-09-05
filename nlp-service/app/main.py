"""ElectriSys - Microservicio de NLP para recomendación de repuestos.

Sprint 2: esqueleto del servicio. /nlp/consultar aún es un eco del texto
preprocesado — la Sprint 3 le añade clasificación de intención y NER, y la
Sprint 4 el motor de recomendación y la generación de respuesta.
"""
from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.preprocessing import normalizar, preprocesar

app = FastAPI(title="ElectriSys NLP Service", version="0.1.0")


class ConsultaRequest(BaseModel):
    texto: str = Field(..., min_length=1, max_length=1000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/nlp/consultar")
def consultar(payload: ConsultaRequest):
    return {
        "texto_original": payload.texto,
        "texto_normalizado": normalizar(payload.texto),
        "tokens": preprocesar(payload.texto),
    }
