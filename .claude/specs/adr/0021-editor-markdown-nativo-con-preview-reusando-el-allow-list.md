# 0021. Editor Markdown nativo con toolbar, reusando el allow-list de renderizado como preview

- **Estado**: accepted
- **Fecha**: 2026-09-01
- **Decisores**: Owner; `grilling` + `design-review` del plan `frontend/markdown-editor` (2026-09-01).
- **Contexto SDD**: refina [ADR-0020](./0020-renderizado-markdown-seguro-con-allow-list.md) (renderizado
  seguro). Traza [CU-FE-04](../frontend/casos-de-uso/CU-FE-04-alta-de-ticket.md),
  [CU-FE-05](../frontend/casos-de-uso/CU-FE-05-detalle-visibilidad-y-mutaciones.md) y
  [CU-FE-06](../frontend/casos-de-uso/CU-FE-06-flujo-ia-cola-draft-decisiones.md) (extensiones nuevas).

## Contexto y planteamiento del problema

ADR-0020 resolvió la **lectura**: `MarkdownText` renderiza de forma segura el Markdown ya escrito
(draft de la IA, mensajes publicados). Quedó sin resolver la **escritura**: los tres sitios donde un
humano compone ese mismo Markdown (`ticket-reply-form.tsx`, `approval-decision.tsx` en modo edición,
`ticket-create-form.tsx`) seguían siendo `<textarea>` planos — el usuario tiene que escribir
`**negrita**` a mano, sin ayuda visual ni vista previa.

## Decision drivers

- El valor que produce el editor debe ser **exactamente** el string que `MarkdownText` ya sabe
  renderizar — sin contrato nuevo, sin cambio de backend.
- Cualquier vista previa en vivo del texto que se está componiendo debe pasar por el **mismo**
  allow-list auditado de ADR-0020, no por un segundo motor de renderizado sin auditar.
- El resultado del toolbar no puede producir sintaxis que el allow-list de `MarkdownText` no sepa
  representar (round-trip roto entre "lo que el botón promete" y "lo que se ve al publicar").

## Opciones consideradas

1. **Editor Markdown-nativo con toolbar** (`@uiw/react-md-editor`), preview sobreescrita con
   `MarkdownText` — elegida.
2. **WYSIWYG completo** (Tiptap/Lexical) sobre un documento interno (HTML/JSON), serializando a/desde
   Markdown en cada carga/guardado.
3. **Toolbar mínima hecha a mano** sobre el `<textarea>` existente (inserción de sintaxis por
   manipulación de `selectionStart`/`selectionEnd`), sin dependencia nueva.

## Resultado de la decisión

**Opción 1.** Los ejes concretos:

### Preview: sobreescrita con `MarkdownText`, no el motor por defecto de la librería

`@uiw/react-md-editor` (`preview="live"`) trae su propio renderizador de Markdown para el panel de
vista previa — un pipeline **distinto** del auditado en ADR-0020, y no seguro por defecto contra HTML
embebido (el propio paquete documenta que hace falta `rehype-sanitize` explícito para eso). Usarlo tal
cual **reabriría ADR-0020 sin decirlo**: el texto que se previsualiza (`approval.draft_body` al editar
un draft de la IA) es exactamente el "origen no confiable" que esa ADR protege.

Se sobreescribe el renderer de preview (prop `components.preview` del editor) para que delegue en
`MarkdownText`. Dos beneficios a la vez: (a) mismo allow-list ya auditado, ningún motor nuevo que
auditar; (b) el preview deja de ser una *aproximación* de cómo se verá el texto — es **exactamente**
el mismo componente que lo renderizará al publicarse (WYSIWYG real, no un WYSIWYG-ish de una librería
distinta).

**Descartado**: `rehype-sanitize` como alternativa — mantendría DOS allow-lists (el de `MarkdownText`
y el de la config de sanitización del editor) que podrían divergir con el tiempo.

### Toolbar completo, con una exclusión

Incluye tabla, imagen (solo URL externa — ver más abajo), código, cita, listas, negrita/cursiva/
tachado, enlace. **Se excluye explícitamente** el comando de casillas de lista-de-tareas
(`checkedListCommand`, `- [ ] texto`): ADR-0020 ya excluye esa sintaxis del allow-list de
`MarkdownText` a propósito (sin estado que persista, un checkbox no-interactivo no tiene sentido de
producto) — dejar el botón en el toolbar produciría un round-trip roto (el usuario ve un checkbox al
componer, y texto plano con corchetes al publicar).

**También se excluye** (`scenario-coverage` del plan) el comando nativo de alternar modo de vista
(edit/live/preview) que trae el toolbar por defecto: dejarlo permitiría al usuario salirse de
`preview="live"`, contradiciendo la decisión de `grilling` de fijar ese modo por consistencia en las
3 superficies.

### Imagen: solo URL externa, sin integración con adjuntos

`GET /messages/{id}/attachments/{attachment_id}` exige `Authorization` (401 sin él, verificado) — no
es una URL pública que un `<img>` de Markdown pueda referenciar (el navegador no envía cabeceras
personalizadas al cargar una imagen). Integrar con el sistema de adjuntos exigiría o bien exponer una
URL pública/firmada en el backend (cambio de contrato, fuera de alcance — este plan es puramente
frontend) o un blob-URL local sin persistencia real entre sesiones (el Markdown guardado apuntaría a
una URL que deja de existir en cuanto otro usuario/pestaña abre el mismo mensaje). El botón de imagen
del toolbar inserta `![alt](url)` con una URL que el usuario pega, igual que ya soporta `MarkdownText`
hoy para imágenes de origen externo.

**Pegar/arrastrar una imagen se verifica y bloquea si hace falta** (`scenario-coverage`): no está
confirmado si `@uiw/react-md-editor` embebe por defecto una imagen pegada/arrastrada como `data:`/
base64 en el propio texto. Si lo hace, contradice directamente "solo URL externa" — no se acepta como
riesgo conocido, se intercepta el evento de paste/drop del editor y se descarta la imagen embebida.

### Integración con `react-hook-form`

`@uiw/react-md-editor` es un componente controlado (`value`/`onChange`), incompatible con
`{...register("body")}` sobre un `<textarea>` nativo. Las dos superficies con formularios RHF
(`ticket-reply-form.tsx`, `ticket-create-form.tsx`) envuelven `MarkdownEditor` con `Controller` de
RHF — primer uso de `Controller` en el repo (verificado, 0 usos previos).

### Theming

`MarkdownEditor` lee el tema activo (`useTheme()`, ya existente en `theme-provider.tsx`) y lo traduce
al atributo `data-color-mode` que espera `@uiw/react-md-editor` — mecanismo de tema independiente del
`.dark` de Tailwind que usa el resto de la app.

### Componente compartido

`frontend/src/components/markdown-editor.tsx` — mismo patrón de ubicación que `markdown-text.tsx`
(primitiva de UI transversal sin feature dueño, precedente ya fijado en ADR-0020/`grilling`).

### Confirmación

CU-FE-04/CU-FE-05/CU-FE-06 (Gherkin, extensiones nuevas) + tarea `frontend-markdown-editor-01`.

## Consecuencias

- **Buena**: la vista previa es literalmente el mismo componente que renderiza el texto ya publicado —
  cero divergencia entre "lo que veo mientras escribo" y "lo que se publica".
- **Buena**: no se abre ninguna superficie de riesgo nueva — `MarkdownText`/ADR-0020 siguen siendo el
  único punto de verdad del allow-list, tanto en lectura como en la preview de escritura.
- **Mala, aceptada**: primer uso de `Controller` de RHF en el repo — patrón nuevo a mantener.
- **Mala, aceptada**: los tooltips traducidos del toolbar (comandos personalizados) no se actualizan
  solos ante un bump de `@uiw/react-md-editor` que cambie sus comandos por defecto — reconciliación
  manual en el futuro.
- **Riesgo aceptado, no mitigado**: si en algún momento anterior a esta decisión se hubiera persistido
  Markdown con `- [ ] texto` (no ha ocurrido — feature nueva), excluir el comando del toolbar no lo
  corrige retroactivamente.

## Pros y contras de las opciones

- **Opción 1 (editor Markdown-nativo, elegida)** — *Pros*: el valor ES el string ya soportado, sin
  conversión; preview reusa el allow-list auditado. *Contras*: primer uso de `Controller` en el repo;
  mantenimiento de comandos personalizados traducidos.
- **Opción 2 (WYSIWYG completo)** — *Pros*: experiencia de edición más pulida. *Contras*: exige
  serializar/deserializar Markdown↔documento interno en cada carga/guardado, con riesgo real de
  pérdida frente al allow-list deliberadamente distinto del HTML completo (ADR-0020) — descartada por
  evidencia de riesgo, no por preferencia.
- **Opción 3 (toolbar hecha a mano)** — *Pros*: cero dependencias nuevas. *Contras*: atajos de
  teclado, accesibilidad del toolbar y vista previa quedan por resolver a mano, sin ganar nada sobre
  una librería madura ya compatible con el stack (React 19 verificado).
