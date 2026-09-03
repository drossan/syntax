# 0020. Renderizado Markdown seguro del texto generado por IA, con allow-list explícito

- **Estado**: accepted
- **Fecha**: 2026-08-31
- **Decisores**: Owner; `grilling` + `design-review` del plan `frontend/markdown-rendering`
  (2026-08-31).
- **Contexto SDD**: materializa FR-029 en [`spec.md`](../frontend/spec.md), y la mitad "allow-list"
  de NFR-004 que ya estaba escrita pero sin implementación. Traza
  [CU-FE-05](../frontend/casos-de-uso/CU-FE-05-detalle-visibilidad-y-mutaciones.md) (extensión 1c) y
  [CU-FE-06](../frontend/casos-de-uso/CU-FE-06-flujo-ia-cola-draft-decisiones.md) (extensiones
  3a-3c). Política de referencia: [`cross-cutting.md`](../frontend/cross-cutting.md) §1 (anti-XSS).

## Contexto y planteamiento del problema

`backend/app/agents/nodes/generate.py::_finalize_draft` redacta el draft del agente en Markdown real
(negrita, listas, una sección "Fuentes" en lista), pero el frontend lo mostraba **literal** —
`ApprovalDecision` y `TicketThread` renderizaban el texto plano, sin interpretar la sintaxis. NFR-004
ya pedía "markdown sanitizado con allow-list"; esta ADR fija cómo.

## Decision drivers

- Cero coste de licencia/mantenimiento nuevo si la librería ya es segura por defecto.
- La garantía anti-XSS (`cross-cutting.md` §1) no puede quedar implícita en "no lo intentamos" — tiene
  que sobrevivir a que el draft del agente empiece a usar sintaxis nueva.
- El allow-list debe ser una única fuente reusada por ambas superficies, no una config duplicada.

## Opciones consideradas

1. **`react-markdown`** (elegida) — renderiza a elementos React reales, nunca a `innerHTML`; sanea
   `href`/`src` por defecto (`defaultUrlTransform`); sin el plugin `rehype-raw`, el HTML embebido en
   el Markdown fuente nunca se parsea.
2. `marked` + `dompurify` — genera HTML crudo, necesita `dangerouslySetInnerHTML` + sanitizar aparte;
   más superficie de ataque a gestionar (dos dependencias, dos puntos de fallo).
3. `markdown-to-jsx` — alternativa igual de segura (React, no `innerHTML`), descartada por ser el
   estándar de facto menos extendido del ecosistema.

## Resultado de la decisión

**Opción 1**, con un componente compartido `frontend/src/components/markdown-text.tsx`:

- `allowedElements` explícito: párrafo, negrita/énfasis, tachado, encabezados `h1`-`h6` (peso visual
  moderado), listas + ítems, tabla completa (con `remark-gfm`), enlace, imagen, código inline/bloque,
  cita, salto de línea. `unwrapDisallowed: true` — lo fuera de lista se desenvuelve a texto, no
  desaparece.
- **`remark-gfm` incluido** (tablas, tachado, autolinks) — decisión explícita del owner, revierte la
  recomendación YAGNI inicial: el draft del agente no usa hoy esa sintaxis, se añade igualmente por
  anticipación del owner.
- **Casillas de lista-de-tareas de GFM excluidas** del allow-list — sin estado que persista, no tiene
  sentido de producto; se desenvuelven a texto plano.
- **`<img>` incluido**, con `referrerPolicy="no-referrer"` + `loading="lazy"` — decisión explícita del
  owner ("trabajaremos con imágenes"); la mitigación evita que cargar una imagen filtre al servidor
  externo en qué ticket está el usuario (vía `Referer`).
- **Sin `rehype-raw`**: es la garantía anti-XSS central — el Markdown fuente nunca se interpreta como
  HTML. Verificado que `react-markdown` es "secure by default" (su propio README, sección
  "Security") y ya aplica `defaultUrlTransform` sin config extra.
- **Renderizado universal**: todos los mensajes del hilo (`TicketThread`), sin condicionar a
  `is_ai_draft` — un solo camino de render. **Riesgo aceptado, no mitigado**: un mensaje humano con
  guiones/asteriscos casuales se reinterpreta como Markdown; si se revirtiera a solo-IA más adelante,
  el render de mensajes históricos cambiaría de significado retroactivamente.
- **Sin `whitespace-pre-wrap`** en `MarkdownText` — los saltos de párrafo/lista los da el HTML real
  que genera `react-markdown`; combinarlo con esa clase duplicaría espaciado. Los wrappers existentes
  (`blockquote` en `ApprovalDecision`, `<p>` en `TicketThread`) pierden esa clase al envolver con
  `MarkdownText`.
- **`React.memo`** en `MarkdownText` — mitigación preventiva sin evidencia de necesidad (decisión del
  owner tras `design-review`), ante el polling extensivo del hilo/notificaciones (`cross-cutting.md`
  §3).

### `stryker.config.json`

`design-review` señaló que `mutate` excluye todos los `.tsx` y que `src/components/**` no está en el
glob — verificado en vivo que **no bloquea el gate de esta tarea**: `pnpm exec stryker run --mutate
"<fichero>"` ignora el `mutate`/exclusiones del config por completo (probado con un fichero de
prueba real, 100% de score). Se corrige el glob igualmente, a petición del owner, como higiene del
repo — **no** incluye llevar el `pnpm exec stryker run` sin acotar (ahora mucho más amplio) a
`break: 80`; eso queda como trabajo aparte.

### Lo que NO se hace

- **Sin `rehype-sanitize`**: innecesario sin plugins de terceros no confiables — `allowedElements` +
  ausencia de `rehype-raw` ya cierran la superficie.
- **Sin sanitización de HTML crudo embebido**: deliberadamente no soportado; si hiciera falta, es una
  decisión de seguridad aparte con su propio plan.
- **Sin tocar `TicketTimeline`**: no renderiza `body`, confirmado leyendo el fichero.

## Consecuencias

- **Buena**: el draft del agente y los mensajes del hilo se leen formateados, cerrando la mitad
  pendiente de NFR-004.
- **Buena**: un único componente/allow-list auditable para el requisito anti-XSS, en vez de lógica
  duplicada por superficie.
- **Mala, aceptada**: el allow-list (GFM, imágenes, encabezados) es más ancho que lo que el generador
  produce hoy — superficie a mantener sin caso de uso real todavía, decisión explícita del owner.
- **Mala, aceptada**: el render universal de mensajes reinterpreta como Markdown texto humano sin
  intención de formato; es una decisión de datos (mensajes ya persistidos), no solo de código.
- **Riesgo operacional, sin alarma**: `pnpm exec stryker run` sin acotar quedará mucho más lento tras
  corregir el glob de `.tsx`, con un volumen de survivors pendientes fuera de este plan.

## Pros y contras de las opciones

- **Opción 1 (`react-markdown`, elegida)** — *Pros*: segura por defecto, sin `innerHTML`, un solo
  paquete. *Contras*: dependencia nueva; con `remark-gfm`, dos paquetes en vez de uno.
- **Opción 2 (`marked` + `dompurify`)** — *Pros*: `marked` es rápido y muy usado. *Contras*: exige
  `dangerouslySetInnerHTML` + sanitizar aparte — dos dependencias, dos puntos de fallo, más superficie
  de ataque a auditar.
- **Opción 3 (`markdown-to-jsx`)** — *Pros*: igual de segura, bundle algo menor. *Contras*: comunidad
  más pequeña; sin ventaja concreta sobre la opción 1 para este caso.
