# ElectriSys — Panel de documentación

Nota de inicio del vault de Obsidian. Desde acá se llega a toda la documentación del proyecto — abrí el **Graph view** (ícono de la barra izquierda) para ver cómo se conectan estos documentos entre sí.

## Visión general

- [[README|README del proyecto]] — arquitectura completa, stack, cómo levantar todo con Docker
- [[ESTRUCTURA|ESTRUCTURA.md]] — historial de la infraestructura distribuida (mTLS, VPN, Istio, monitoreo, análisis de red)

## Asistente NLP (Aplicación de la Inteligencia Artificial)

- [[docs/asistente-nlp|Arquitectura del asistente NLP]] — pipeline propio: intención → NER → recomendación → NLG
- [[docs/asistente-casos-limite|Casos límite y resiliencia]] — rate limiting, fallos del microservicio/backend
- [[nlp-service/docs/evaluacion|Evaluación cuantitativa]] — accuracy de intención, precisión de NER, precisión@k del recomendador

## Migración a Oracle (Gestión de Base de Datos)

- [[oracle/docs/migracion-oracle|Migración del modelo relacional a Oracle 23ai]] — PL/SQL, triggers, vistas, roles/privilegios, planes de ejecución, backup/recovery

## Infraestructura distribuida (Sistemas Distribuidos)

Sin documento propio todavía más allá de `ESTRUCTURA.md` y el `README.md` — corresponde a las carpetas `docker/`, `k8s/`, `tls/`, `vpn/`, `monitoring/`, `network-analysis/`.
