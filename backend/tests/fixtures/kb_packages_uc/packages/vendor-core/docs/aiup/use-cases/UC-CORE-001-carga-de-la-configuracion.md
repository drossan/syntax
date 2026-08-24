---
id: UC-CORE-001
dominio: platform-and-devex
estado: draft
traza:
  - src/config/loadConfig.ts
  - src/config/schema.ts
---

# Carga de la configuración del proyecto

## Comportamiento

La configuración del proyecto se resuelve al arrancar: se lee el fichero de configuración de la raíz, se
valida contra el esquema declarado y se expone al resto de la aplicación ya normalizada. Si el fichero no
existe, el arranque continúa con los valores por defecto y lo registra; si existe pero no valida, el
arranque falla con el detalle de los campos inválidos.

## Conceptos

- **Configuración del proyecto** — el conjunto de valores que definen cómo se comporta la instancia.
- **Esquema** — la declaración de qué campos existen, de qué tipo y cuáles son obligatorios.

## Reglas e invariantes

- **AC1** — Un fichero de configuración ausente nunca impide el arranque.
- **AC2** — Un fichero de configuración presente pero inválido siempre impide el arranque.
