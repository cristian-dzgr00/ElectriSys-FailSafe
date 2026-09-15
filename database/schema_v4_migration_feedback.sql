-- ============================================================
-- ElectriSys POS - Migración v4.0 (Feedback del asistente NLP)
-- Ejecutar DESPUÉS de schema_v3_migration_nlp.sql
-- ============================================================

USE electrisys;

-- ── Feedback de curación manual (active learning asistido) ─────────
-- Reutiliza consultas_asistente en vez de crear una tabla nueva: cada fila
-- ya representa una consulta con su intención/entidades/respuesta, el
-- feedback es solo un dato adicional sobre esa misma fila.
-- NULL = sin feedback todavía, 1 = útil (👍), 0 = no útil (👎).
ALTER TABLE consultas_asistente
    ADD COLUMN util TINYINT(1) DEFAULT NULL AFTER respuesta_json,
    ADD INDEX idx_consultas_util (util);
