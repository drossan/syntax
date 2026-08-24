---
id: UC-CORE-002
dominio: search-ai-and-llms
estado: active
traza:
  - src/hooks/useRelatedContent.ts
---

# Contenido relacionado de una página

## Comportamiento

Para la página actual se resuelve un listado de contenido relacionado calculado por IA. Si falta alguno
de los datos de contexto (instancia, sitio o idioma), la resolución corta antes de consultar y no
devuelve nada, el mismo patrón descrito en [[UC-CORE-001]].

## Reglas e invariantes

- **AC1** — Sin contexto completo no se consulta el servicio de relacionados.
