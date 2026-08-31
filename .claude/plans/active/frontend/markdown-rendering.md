---
id: frontend-markdown-rendering
package: frontend
status: active
branch: plan/frontend/markdown-rendering
issue:
created: 2026-08-31
updated: 2026-08-31
---

# Renderizado Markdown seguro del texto generado por IA

## Contexto y problema

`backend/app/agents/nodes/generate.py::_finalize_draft` ya redacta el draft en Markdown real
(negritas `**texto**`, listas numeradas, y una sección final `Fuentes:\n- [UC-ID] título (tipo)` en
formato de lista) — confirmado leyendo el código. El frontend, hoy, muestra ese texto **literal**
(sin renderizar) en dos superficies:

- `frontend/src/features/approvals/approval-decision.tsx:70` — el `<blockquote>` con `draft_body`
  durante la revisión HITL.
- `frontend/src/features/tickets/ticket-thread.tsx` — el `<p>{message.body}</p>` del hilo, una vez
  el mensaje ya se publicó (aprobado o auto-resuelto).

(`TicketTimeline` NO renderiza `body` — solo tipo/actor/fecha — confirmado leyendo el fichero; no es
una tercera superficie.)

Verificado en vivo: el revisor ve `**negrita**` y `1. paso` literales, no una respuesta formateada.

**El spec ya anticipaba esto.** `.claude/specs/frontend/spec.md` NFR-004 dice literalmente: *"Anti-XSS:
contenido externo como texto inerte; **markdown sanitizado con allow-list**"*, y
`cross-cutting.md` §1 exige *"Si hay markdown, sanitizar (allow-list)"* + un *"test mínimo por
superficie que renderice contenido externo: marcado tipo script se muestra como texto y no se
ejecuta"*. El texto plano de hoy era el paso intermedio seguro; este plan cumple la otra mitad del
NFR que ya estaba escrita.

`package.json` no tiene ninguna librería de Markdown/sanitización — confirmado con grep. Añadir
**`react-markdown`** (decisión del owner, ya tomada): renderiza a elementos React reales, nunca a
`innerHTML` — sin el plugin `rehype-raw` (que este plan NO añade), el Markdown fuente nunca se
interpreta como HTML: un `<script>` literal en el texto de origen se muestra como texto, no se
ejecuta. Esa propiedad, más un **allow-list explícito** de elementos permitidos (prop
`allowedElements` de `react-markdown`), es la implementación concreta del "allow-list" que NFR-004
ya pedía — no una interpretación nueva.

## Objetivos

1. **El texto generado por IA se renderiza formateado** (negritas, listas) en las dos superficies
   donde el usuario lo lee — el draft en revisión y el mensaje ya publicado en el hilo.
   - *Criterio de éxito*: un texto con `**negrita**` y una lista `1. paso` se ve formateado (no
     literal) en `ApprovalDecision` y en `TicketThread`; verificación manual contra el backend real
     (crear un ticket, ver un draft real generado por el LLM formateado en ambas superficies).
2. **La garantía anti-XSS de NFR-004 se mantiene explícita**, no implícita en "no lo intento".
   - *Criterio de éxito*: test por superficie (el que exige `cross-cutting.md` §1) que confirma que
     un `<script>`/`<img onerror=...>` embebido en el texto de origen se renderiza como texto inerte,
     nunca se ejecuta ni se inyecta como HTML.

## Alcance y fuera de alcance

### Dentro del alcance
- **Dependencias nuevas** (`grilling`, 2026-08-31 — revierte la recomendación YAGNI inicial del
  plan, decisión explícita del owner): `react-markdown` **y** `remark-gfm` (tablas, tachado,
  autolinks, listas de tareas), aunque el draft del agente no use hoy esa sintaxis extendida.
- **Componente compartido nuevo** `frontend/src/components/markdown-text.tsx` (`grilling` — crea el
  precedente de un directorio para primitivas de UI transversales sin feature dueño) que envuelve
  `<ReactMarkdown remarkPlugins={[remarkGfm]}>` con:
  - `allowedElements`: allow-list explícita — párrafo, negrita/énfasis, tachado (`del`), encabezados
    `h1`-`h6` (`grilling`: con peso visual moderado — `text-base font-semibold`, no tamaños de
    portada, para no romper la jerarquía dentro de una card), listas ordenadas/no ordenadas + ítems,
    enlace (`scenario-coverage`: `target="_blank" rel="noopener noreferrer"` — mismo criterio que
    cualquier enlace a dominio externo, sin arriesgar la sesión SPA cuyo access-token vive en memoria,
    FR-003), imagen (`grilling`: sí se incluye — decisión explícita del owner, "trabajaremos con
    imágenes"), código inline/bloque, cita, tabla completa (`table`/`thead`/`tbody`/`tr`/`th`/`td`,
    `grilling`: si se asume GFM, el allow-list debe soportar lo que esa sintaxis produce, con
    estilos básicos de borde/padding — desenvolver una tabla a texto plano sería peor que no
    soportarla), separador horizontal (`hr`, `scenario-coverage`: sin decisión explícita antes, se
    incluye en el allow-list — con `unwrapDisallowed` un `hr` no tiene texto que conservar y
    desaparecería en silencio, distinto del resto de exclusiones documentadas), salto de línea.
  - **Excluidos deliberadamente del allow-list** (`grilling`): las casillas de lista-de-tareas de
    GFM (`- [ ] paso`) — un checkbox no-interactivo sin estado que persista no tiene sentido de
    producto aquí; se desenvuelven a texto plano (`[ ] paso`).
  - `<img>` con `referrerPolicy="no-referrer"` y `loading="lazy"` (`grilling`) — sin esto, cargar una
    imagen externa filtraría al servidor de esa imagen en qué ticket está el usuario (vía el header
    `Referer`); la mitigación no bloquea la decisión de soportar imágenes, solo evita esa fuga
    lateral.
  - `unwrapDisallowed`: los elementos fuera del allow-list se "desenvuelven" (se conserva su texto,
    se descarta la etiqueta) en vez de desaparecer en silencio — evita que contenido legítimo se
    pierda por un elemento no contemplado.
  - Sin `rehype-raw` (HTML embebido en el Markdown fuente nunca se parsea — la garantía anti-XSS
    central). **Verificado en `grilling`**: `react-markdown` ya sanea `href`/`src` con su propio
    `defaultUrlTransform` (aplicado automáticamente, sin config extra) — un `javascript:` en un
    enlace o imagen queda neutralizado sin necesitar `urlTransform` propio; confirmado en su README
    ("Security" — "secure by default").
  - Un único punto de auditoría para el test anti-XSS exigido por `cross-cutting.md` §1, reusado por
    ambas superficies en vez de duplicar la config del allow-list dos veces.
  - Sin `whitespace-pre-wrap` (`design-review` #5) — los saltos de párrafo/lista los da el propio
    HTML que genera `react-markdown` (`<p>`, `<li>`...); combinar eso con `whitespace-pre-wrap`
    duplicaría espaciado. Convención fijada aquí, no en las tareas 02/03.
  - `React.memo` (`design-review` #6, decisión del owner — sin evidencia de que haga falta, mitigación
    preventiva ante re-render en cada tick de polling del hilo).
- **Reemplazar** el `<blockquote>{approval.draft_body}</blockquote>` de `approval-decision.tsx` y el
  `<p>{message.body}</p>` de `ticket-thread.tsx` por `<MarkdownText>{...}</MarkdownText>`, quitando
  `whitespace-pre-wrap` de ambos wrappers (ahora lo da `MarkdownText`, ver arriba).
- **`ticket-thread.tsx` renderiza TODOS los mensajes por igual** (`grilling` + confirmado en
  `design-review` #1) — sin condicionar a `is_ai_draft`: un mensaje escrito a mano por soporte con
  `**texto**` también se renderiza en negrita. Un solo camino de render, sin rama `if`. **Riesgo
  aceptado, no mitigado** (`design-review` #1): un mensaje humano con guiones/asteriscos casuales sin
  intención de formato se reinterpreta como Markdown; si más adelante se revierte a solo-IA, el
  render de mensajes históricos ya guardados cambia de significado retroactivamente. Cubierto por un
  test de que ese caso se sigue leyendo razonablemente (no que no se transforme).
- Test anti-XSS explícito en **cada** superficie tocada (`approval-decision.test.tsx`,
  `ticket-thread.test.tsx`), no solo en el componente compartido — cumple literalmente "test mínimo
  **por superficie**" de `cross-cutting.md` §1, no solo una vez a nivel de unidad del componente base.
- Tests del propio `MarkdownText` (negrita → `<strong>`, lista → `<ul>/<ol>`, tabla, encabezado,
  imagen con los atributos de mitigación, enlace, el caso adversario del script/HTML embebido,
  Markdown truncado a mitad de sintaxis (`design-review` #4 — `_finalize_draft` trunca
  `raw_draft[:4000]` antes de anexar "Fuentes"; verificar que no rompe el render), y texto humano
  con guiones/asteriscos casuales sin intención de formato (`design-review` #1)).
- **Corregir `frontend/stryker.config.json`** (`design-review` #3, ampliado a petición del owner):
  el `mutate` array excluye TODOS los `.tsx` (`"!src/**/*.tsx"` anula la inclusión de la línea
  anterior) y `src/components/**` no está en el glob en absoluto. Se corrige el glob para que un
  `pnpm exec stryker run` **sin acotar** también cubra `.tsx`/`src/components/**` — **no** forma
  parte de esta tarea llevar ese run completo (ahora mucho más amplio) a `break:80`; eso queda como
  trabajo aparte, señalado para el owner. El gate de mutation **de las tareas de este plan** ya
  funciona hoy sin este cambio — verificado en `design-review`: `pnpm exec stryker run --mutate
  "<fichero>"` ignora el `mutate`/exclusiones del config por completo (probado con un fichero real en
  `src/components/`, 100% de score, 8 mutantes matados) — el fix del config es higiene del repo, no
  un requisito para que el gate de esta tarea funcione.

### Fuera de alcance
- Tocar `TicketTimeline` — no renderiza `body`, confirmado; no es una superficie de este plan.
- La rama `chore/frontend/ux-audit` (truncado "ver más/ver menos" con `line-clamp` sobre
  `approval-decision.tsx`, aún sin mergear a `main`): el truncado es CSS visual sobre el contenido
  YA renderizado (`line-clamp-N`), no recorta el string Markdown crudo — compatible sin cambios
  adicionales cuando esa rama se integre, pero **no se toca aquí** (esta rama parte de `main`, que no
  tiene ese código todavía).
- Sanitización de HTML crudo embebido vía `rehype-raw`/`dompurify` — deliberadamente NO se soporta
  HTML crudo en el Markdown fuente (ni el agente lo genera hoy); si se necesitara en el futuro, es
  una decisión de seguridad aparte, con su propio plan.
- Casillas de lista-de-tareas de GFM en el allow-list (ver decisión de `grilling` arriba).
- Markdown en cualquier otro campo de texto libre del producto (asunto de ticket, notas internas,
  nombres) — NFR-004 ya los trata como "texto inerte" sin más; este plan no reabre esa superficie.

## Recursos externos

- `.claude/specs/frontend/spec.md` NFR-004 y `cross-cutting.md` §1 — fuente de verdad del requisito
  (ya escrito, este plan lo implementa).
- `backend/app/agents/nodes/generate.py::_finalize_draft` — formato real del texto a renderizar
  (negrita + lista + sección "Fuentes").
- `frontend/src/features/approvals/approval-decision.tsx` y
  `frontend/src/features/tickets/ticket-thread.tsx` — las dos superficies a tocar.
- [react-markdown](https://github.com/remarkjs/react-markdown) v10.1.0 (verificado con
  `npm view react-markdown version`), peer deps `react >= 18` (el repo usa React 19.2.8 — compatible).

## Estimación global

- **Tareas totales**: 4 (ver lista al final; creció de 3 a 4 en `design-review` al separar el fix de
  `stryker.config.json` como pieza propia, sin dependencia de las demás).
- **Esfuerzo estimado**: 1-1.5 sesiones.
- **Recursos**: dos dependencias nuevas (`react-markdown` + `remark-gfm`, sin coste de licencia — MIT).

## Criterios de calidad y verificación

- TDD en todas las capas; tests antes de la implementación.
- `pnpm lint` y `pnpm typecheck` en verde tras cada tarea cerrada.
- Gate de mutation testing (Stryker, `break: 80`) por tarea.
- Test anti-XSS explícito por superficie (mandato de `cross-cutting.md` §1), no opcional.
- Verificación manual contra el backend real: un draft real del LLM (con negrita/listas) se ve
  formateado en la cola de aprobaciones y, tras aprobarlo, en el hilo del ticket.

## Tasks

- [x] `frontend-markdown-rendering-01` (P1) — Componente compartido `MarkdownText` con allow-list y garantía anti-XSS  · depends_on: —
- [ ] `frontend-markdown-rendering-02` (P2) — Renderizar el draft con `MarkdownText` en `ApprovalDecision`  · depends_on: frontend-markdown-rendering-01
- [ ] `frontend-markdown-rendering-03` (P2) — Renderizar el body del mensaje con `MarkdownText` en `TicketThread`  · depends_on: frontend-markdown-rendering-01
- [ ] `frontend-markdown-rendering-04` (P3) — Corregir la exclusión de `.tsx`/`src/components/**` en `stryker.config.json`  · depends_on: —

## Registro de cambios del plan

- 2026-08-31: creado, a partir de un bug real reportado en pruebas manuales (el draft de la IA se
  veía como Markdown literal, no formateado) — decisiones ya tomadas con el owner: librería
  (`react-markdown`), alcance (draft + hilo publicado), y proceso (`/plan-task` completo, no fix
  directo, por la dependencia nueva + superficie de seguridad real).
- 2026-08-31: refinado con `grilling` (7 preguntas, 7 decisiones):
  1. `ticket-thread.tsx` renderiza TODOS los mensajes (no solo `is_ai_draft`) — un solo camino,
     sin rama condicional.
  2. `remark-gfm` SÍ se añade ya (revierte la recomendación YAGNI del borrador inicial) — decisión
     explícita del owner.
  3. Encabezados `h1`-`h6` SÍ entran en el allow-list, con peso visual moderado.
  4. Tablas GFM completas SÍ entran en el allow-list, con estilos básicos — desenvolverlas a texto
     plano sería peor que soportarlas, dado que ya se asume GFM.
  5. Tachado (`del`) SÍ entra; casillas de lista-de-tareas NO (sin estado que persista, se
     desenvuelven a texto plano).
  6. `MarkdownText` vive en `frontend/src/components/markdown-text.tsx` (precedente nuevo: primitiva
     de UI transversal sin feature dueño).
  7. `<img>` SÍ entra en el allow-list (decisión explícita del owner, "trabajaremos con imágenes"),
     con `referrerPolicy="no-referrer"` + `loading="lazy"` para evitar la fuga de `Referer` a
     servidores externos al cargar una imagen embebida.
  - Verificado durante `grilling` (hecho, no decisión): `react-markdown` sanea `href`/`src`
    automáticamente vía `defaultUrlTransform` — un `javascript:` en un enlace o imagen queda
    neutralizado sin config adicional (confirmado en su README, sección "Security": "secure by
    default"). No hace falta `urlTransform` propio ni `rehype-sanitize`.
- 2026-08-31: revisado con `design-review` (subagente adversario, 6 hallazgos, model routing caído a
  inherit — `models.design-review: claude-opus-4-8` no es un alias válido). Decisiones, con el owner:
  1. Render universal de mensajes (`grilling` #1) — se mantiene; se añade test de "texto humano
     casual no se rompe" y se documenta como riesgo aceptado, no mitigado.
  2. Allow-list ancho (GFM/imágenes/h1-h6) — se mantiene sin cambios; ya era una decisión explícita
     de `grilling`, el hallazgo no aporta un hecho nuevo.
  3. **Hallazgo corregido tras verificación propia, no aceptado tal cual**: el subagente afirmó que
     el gate de mutation no podría cubrir `markdown-text.tsx` (exclusión `.tsx` + `src/components/`
     fuera del glob `mutate`). Probado en vivo: `pnpm exec stryker run --mutate "<fichero>"` ignora
     el `mutate`/exclusiones del config por completo (100% score sobre un fichero de prueba en
     `src/components/`) — el gate de las tareas de este plan ya funciona sin tocar nada. Aun así, a
     petición del owner, se corrige `stryker.config.json` igualmente (nueva tarea `04`, sin
     dependencia de las demás) — higiene del repo, no requisito de este plan; no incluye llevar el
     run completo (ahora mucho más amplio) a `break:80`.
  4. Test de Markdown truncado a mitad de sintaxis (`_finalize_draft` trunca antes de anexar
     "Fuentes") — incorporado a los escenarios de `MarkdownText`.
  5. Convención de espaciado (`whitespace-pre-wrap` fuera, lo da el HTML de `react-markdown`) fijada
     en la tarea `01`, no dejada para que `02`/`03` la decidan cada una por su cuenta.
  6. `React.memo` en `MarkdownText` — añadido a petición del owner como mitigación preventiva, sin
     evidencia de que el re-render en cada poll sea un problema real (el propio `design-review` lo
     marcó como hipótesis sin reproducir).
- 2026-08-31: endurecido con `scenario-coverage` (subagente QA, hallazgos en (A) dentro de alcance;
  (B) fuera de alcance: **ninguno**). Decisiones, con el owner:
  1. **Hallazgo crítico corregido**: `Message.body` en el schema generado es `body?: string`
     (opcional) — la Spec de la tarea `03`, tal cual estaba escrita, no pasaba `pnpm typecheck` al
     envolver con `MarkdownText` (`children: string`). Corregido: `message.body ?? ""`.
  2. `hr` (separador horizontal) SÍ entra en el allow-list, como un `<hr>` fino — antes no tenía
     decisión explícita y se habría desenvuelto en silencio (sin texto que conservar).
  3. Enlaces con `target="_blank" rel="noopener noreferrer"` — evita el vector de *reverse
     tabnabbing* y no arriesga la sesión SPA. Se planteó también la opción de un modal con el
     contenido enlazado embebido en un `iframe`; descartada por abrir una superficie de seguridad
     nueva (sandboxing de iframe, CSP, `X-Frame-Options`) ajena al alcance de este plan.
  4. Incorporados a los escenarios de `MarkdownText` (tarea `01`): código inline/bloque, cita,
     lista ordenada Y no ordenada (no solo una), `children` vacío/solo-espacios, enlace/imagen con
     `javascript:` neutralizado, casilla de tarea GFM desenvuelta a texto plano, autolink, el
     formato exacto de `_finalize_draft` end-to-end, `alt` de imagen preservado.
  5. Incorporado a la tarea `03`: escenario de "texto humano casual no se rompe" repetido a nivel
     `TicketThread` (no solo en `MarkdownText` aislado) — lo exige `cross-cutting.md` §1 ("test
     mínimo por superficie").
  6. Descartado sin incorporar (con motivo, decisión del owner): distinguir `draft_body: undefined`
     vs `""` como escenarios separados (ya cubierto por código, valor bajo); desync del `textarea`
     de edición si el draft cambia en vivo (preexistente, no de este plan); auditoría a11y completa
     (deuda ya conocida del repo, no de este plan); `overflow-wrap` de palabras largas (cosmético);
     reutilización del componente sin fuga de estado (trivial, componente puro).
