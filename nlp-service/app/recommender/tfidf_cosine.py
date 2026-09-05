"""Motor de recomendación por similitud TF-IDF + coseno.

Rankea los repuestos candidatos (ya filtrados por compatibilidad de
vehículo en el backend) según qué tan parecida es su descripción a la
consulta del usuario. El vectorizador se construye por consulta — el
catálogo de candidatos que llega aquí es chico (decenas de productos de
una categoría/vehículo, no miles), así que no hace falta cachear un
vectorizador global entre requests.
"""
import logging

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.preprocessing import preprocesar
from app.recommender.base import EstrategiaSimilitud

logger = logging.getLogger(__name__)


class SimilitudTfidfCoseno(EstrategiaSimilitud):
    def rankear(self, consulta: str, candidatos: list[dict]) -> list[dict]:
        if not candidatos:
            return []

        textos_candidatos = [
            f"{c.get('nombre', '')} {c.get('descripcion') or ''} {c.get('categoria') or ''}"
            for c in candidatos
        ]
        corpus = [consulta] + textos_candidatos

        try:
            vectorizador = TfidfVectorizer(tokenizer=preprocesar, token_pattern=None)
            matriz = vectorizador.fit_transform(corpus)
            similitudes = cosine_similarity(matriz[0], matriz[1:])[0]
        except ValueError:
            # Vocabulario vacío (ej. consulta y candidatos sin ningún token en
            # común tras quitar stopwords) — no debería pasar en la práctica,
            # pero mejor no crashear: se devuelven sin ordenar y similitud 0.
            logger.warning("No se pudo vectorizar para el ranking (vocabulario vacío)")
            similitudes = [0.0] * len(candidatos)

        resultado = []
        for candidato, score in zip(candidatos, similitudes):
            item = dict(candidato)
            item["similitud"] = float(score)
            resultado.append(item)

        resultado.sort(key=lambda x: x["similitud"], reverse=True)
        return resultado
