"""ElectriSys - Microservicio de NLP para recomendación de repuestos.

Sprint 5: /nlp/consultar exige el header X-Internal-Key cuando
NLP_INTERNAL_KEY está configurado — evita que cualquiera dentro de la
red de Docker pueda usar el microservicio; solo el backend PHP conoce
la clave (ver backend/src/patterns/observer/GestorAsistente.php).
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app import config
from app.intent.train import MODEL_PATH, entrenar
from app.pipeline import procesar_consulta


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not Path(MODEL_PATH).exists():
        entrenar()
    yield


app = FastAPI(title="ElectriSys NLP Service", version="0.5.0", lifespan=lifespan)


class ConsultaRequest(BaseModel):
    texto: str = Field(..., min_length=1, max_length=1000)


def _verificar_clave_interna(x_internal_key: str = Header(default="")) -> None:
    if config.NLP_INTERNAL_KEY and x_internal_key != config.NLP_INTERNAL_KEY:
        raise HTTPException(status_code=401, detail="Clave interna inválida o ausente")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/nlp/consultar", dependencies=[Depends(_verificar_clave_interna)])
def consultar(payload: ConsultaRequest):
    return procesar_consulta(payload.texto)
