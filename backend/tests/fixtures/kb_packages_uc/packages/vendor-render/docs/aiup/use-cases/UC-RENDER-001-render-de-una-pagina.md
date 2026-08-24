---
id: UC-RENDER-001
dominio: rendering-and-publishing
estado: active
traza:
  - src/render/renderPage.ts
---

# Render de una página publicada

## Comportamiento

Una página publicada se renderiza a partir de su contenido estructurado y de la plantilla de su tipo. El
render es determinista: el mismo contenido y la misma plantilla producen siempre la misma salida.

## Reglas e invariantes

- **AC1** — Una página no publicada nunca se renderiza en producción.
