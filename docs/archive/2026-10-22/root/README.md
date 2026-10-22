# Arquivado em 2026-10-22 — dashboard do Interior Studio (:8782)

`docker-compose.yml` (raiz) e `tools/Dockerfile.dashboard` subiam um container que rodava `tools/studio_dashboard.py`.
Esse script **não existe mais** desde a remoção do NOC/cockpit e dos dashboards (2026-07-24), então o compose não subia nada
útil. Decisão D-002 da FP-043 executada com a autorização do Felipe de 2026-10-22 ("todas as permissões"): arquivado, não
apagado. O compose do RAG (`docker-compose.rag.yml`, Qdrant) continua vivo na raiz.

Restaurar = mover de volta (`git mv`) e recriar o `tools/studio_dashboard.py`.
