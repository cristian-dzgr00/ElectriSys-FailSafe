"""Interfaz Strategy para el motor de similitud del recomendador.

Replica en Python el patrón Strategy que ya usa el backend PHP para el
cálculo de descuentos (DiscountStrategy en backend/src/patterns/strategy):
hoy hay una sola implementación concreta (TF-IDF + coseno), pero queda
listo para intercambiarla (ej. por embeddings) sin tocar el resto del
pipeline.
"""
from abc import ABC, abstractmethod


class EstrategiaSimilitud(ABC):
    @abstractmethod
    def rankear(self, consulta: str, candidatos: list[dict]) -> list[dict]:
        """Recibe la consulta del usuario y una lista de repuestos candidatos
        (dicts con al menos 'nombre', puede traer 'descripcion'/'categoria'),
        y devuelve la misma lista ordenada de mayor a menor similitud, con
        un campo 'similitud' (float 0-1) agregado a cada dict."""
        raise NotImplementedError
