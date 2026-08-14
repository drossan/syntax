# Task Lifecycle

Los directorios `.claude/plans/` y `.claude/tasks/` gobiernan cómo se descompone,
se sigue y se cierra el trabajo en este repo. Esta guía es la **referencia
canónica** para humanos y agentes. Cualquier desviación se motiva y se registra en
el **Registro de cambios** del plan afectado.

> Este fichero lo materializa la skill `/plan-task` (plugin `task-pipeline`) desde su
> plantilla. Ajústalo a las particularidades del repo (lista de packages, runner
> de tests, comandos) pero conserva el esqueleto: estados, ramas, gates y DoD.

## Configuración del repo (`.claude/task-pipeline.yml`)

Algunas fases del pipeline son **opcionales y configurables por repo** en
`.claude/task-pipeline.yml`. Las skills lo leen y lo respetan. **Resolución**:
defaults internos (= preset `full`) → preset de `mode:` → claves explícitas en
`stack:`/`features:`. **Sin archivo → todo `full`** (comportamiento histórico).

**`mode:`** fija los defaults de las features:

| `mode` | `tdd` | docs | `mutation-gate` | Para |
|---|---|---|---|---|
| `full` (default) | ON | ON | `80` | repos con stack de tests sano |
| `legacy` | ON | ON | OFF | legacy: testeas lo que tocas, pero no llegas a 80 |
| `docs-only` | OFF | ON | OFF | solo orquestar planes + documentar |

**`stack:`** (`language`, `package-manager`, `test-runner`, `mutation-tool`): las
skills eligen comandos con esto en vez de asumir pnpm/Vitest/Stryker.

**`features:`** (una clave explícita pisa el preset):

| Flag | Valores | Controla |
|---|---|---|
| `features.tdd` | `true`/`false` | Exigir tests/TDD (1 test por escenario) en la DoD. |
| `features.closing-documentation.tsdoc` | `true`/`false` | Doc en el código en la DoD. |
| `features.closing-documentation.technical-docs` | `true`/`false` | Doc técnica (README/CLAUDE.md/specs/ADRs). |
| `features.closing-documentation.context-log` | `true`/`false` | Session log en `.claude/context/`. |
| `features.mutation-gate` | `false`/`true`(=80)/`<int>` | Gate de mutation y su umbral `break`. |
| `features.github-tracking` | bloque; opt-in (default `off`) | **Comportamiento** opt-in (no gate de DoD): proyección one-way md→GitHub (plan→issue padre, tarea→sub-issue). **No** forma parte de ningún preset; su **ausencia no es drift** para `/doctor`. Solo `enabled: true` activa; valor no-canónico → off. |

Una capa/gate desactivada deja de ser obligatoria: no entra en la DoD ni bloquea
el cierre. **Los dos checkpoints humanos (`grilling` y la aprobación del plan) NO
son configurables** — son por diseño.

## Layout de directorios

```
.claude/
  plans/
    pending/<package>/<name-plan>.md
    active/<package>/<name-plan>.md
    completed/<package>/<name-plan>.md
    cancelled/<package>/<name-plan>.md
  tasks/
    pending/<package>/<task-id>.md
    active/<package>/<task-id>.md
    completed/<package>/<task-id>.md
    cancelled/<package>/<task-id>.md
  context/<package>/<task-id>.md      # session log — append-only
  specs/<package>/HOW-TO-START-A-TASK.md
```

- `<package>` es el nombre de un workspace del repo.
- `<name-plan>` es kebab-case **sin sufijo numérico ambiguo** (p.ej.
  `bootstrap-foundation`, **no** `phase-01`): el `<task-id>` lo embebe y debe poder
  separarse de forma inequívoca (ver abajo).
- `<plan-id>` es **`<package>-<name-plan>`** (p.ej. `api-bootstrap-foundation`). Único
  por plan y ya conocido por `/plan-task`.
- `<task-id>` es **`<plan-id>-<nn>`** (p.ej. `api-bootstrap-foundation-01`), donde
  `<nn>` es un **correlativo DENTRO del plan desde `01`** — el **último segmento de 2
  dígitos** del id. **NO es un contador global del package**: el espacio de nombres del
  id coincide con la unidad de paralelismo (plan = rama), de modo que dos planes
  distintos nunca generan ids que colisionen. Estable para siempre, aunque cambie la
  prioridad.
  - **Parseo inequívoco (por qué `<name-plan>` no acaba en número)**: como el id es
    `<plan-id>-<nn>` y `<nn>` son los **2 últimos dígitos**, un `<name-plan>` acabado en
    número lo hace irrecuperable — `name-plan = phase-01` daría `api-phase-01-01`, donde
    no se distingue si el plan es `phase` (tarea `01-01`) o `phase-01` (tarea `01`). Por
    eso el `<name-plan>` va en kebab-case **sin sufijo numérico ambiguo**.
  - **Formato de `<nn>`**: 2 dígitos con cero a la izquierda desde `01` (`01`, `02`, …,
    `09`, `10`). A partir de la tarea **100** pasa a 3 dígitos (`100`); mantener el ancho
    fijo dentro de un tramo preserva el orden lexicográfico (un plan de 100+ tareas suele
    ser señal de que hay que partirlo).
  - **Coherencia `plan:` ↔ `id`**: el campo `plan:` del frontmatter de la tarea es el
    `<name-plan>` y **debe coincidir** con el `<name-plan>` embebido en el `id`.
  - **Convivencia con ids legacy**: los ids ya creados con el **esquema anterior**
    (`<package>-<nnn>`, contador global del package — p.ej. `api-001`, `api-012`) son
    estables y **no se renumeran**; conviven con los nuevos ids plan-scoped (histórico
    mixto de ids opacos). El esquema nuevo aplica solo a planes/tareas nuevos.

La carpeta es un índice; el `status:` del frontmatter es la fuente de verdad.
**Nunca muevas un fichero sin actualizar `status:`, ni actualices `status:` sin
mover el fichero** — son una sola operación conceptual.

## Plantilla de plan

```markdown
---
id: <package>-<name-plan>
package: <package>
status: pending          # pending | active | completed | cancelled
branch: plan/<package>/<name-plan>
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# <Título del plan>

## Contexto y problema
## Objetivos                  # cada uno con su *criterio de éxito* observable
## Alcance y fuera de alcance
## Recursos externos
## Estimación global
## Criterios de calidad y verificación
## Tasks
- [ ] `<plan-id>-01` (P1) — <título corto>  · depends_on: —
- [ ] `<plan-id>-02` (P2) — <título corto>  · depends_on: <plan-id>-01

## Registro de cambios del plan
- YYYY-MM-DD: creado
```

## Plantilla de tarea

````markdown
---
id: <plan-id>-<nn>        # <plan-id> = <package>-<name-plan>; <nn> correlativo del plan desde 01 (2 díg.)
package: <package>
plan: <name-plan>         # = <name-plan> embebido en id (deben coincidir)
status: pending          # pending | active | blocked | in-review | done | cancelled
priority: 1
depends_on: []
estimate: 2h
actual:
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# <Título de la tarea>

## Description
## Spec
## Fuera de alcance
<!-- Heredado del `### Fuera de alcance` del plan: los bullets que acotan ESTA tarea. Si el plan no
     lo tiene, está vacío, o la tarea se crea sin plan → `—` explícito, nunca el placeholder crudo.
     Acota el encargo, no el esfuerzo: lo que sí está dentro se termina entero. -->
## Scenarios (Gherkin)
<!-- Cada escenario es la fuente 1:1 de un test TDD — el `Then` es el assert.
     Cubre camino feliz Y bordes/errores (el mutation testing los exige). Si la
     tarea no produce código testeable, justifícalo aquí y di cómo se verifica.

     REGLAS (en orden de impacto en la calidad del test):
     1. Declarativo, NO imperativo: el `When` es acción de dominio (qué se hace),
        no pasos de UI/clicks/llamadas internas. Imperativo = test acoplado a la
        implementación que se rompe en cada refactor.
     2. Un escenario = un comportamiento: si hay When…Then…When…Then, son dos.
        Cada uno falla por UNA sola razón.
     3. Disciplina G/W/T: Given = estado previo; When = UNA acción; Then = resultado
        observable. Condiciones/resultados extra con `And`/`But`, no encadenando pasos.
     4. Variaciones del MISMO comportamiento (fronteras, off-by-one) → `Scenario
        Outline` + `Examples`, no copiar escenarios casi iguales. -->
```gherkin
Feature: <capacidad bajo esta tarea>

  Scenario: <caso concreto>
    Given <precondición>
    When <acción de dominio — qué se hace, no cómo se invoca>
    Then <resultado observable y verificable>

  Scenario: <error / borde>
    Given ...
    When ...
    Then <error esperado, código, efecto>

  # Fronteras / clases de equivalencia del mismo comportamiento.
  # <entrada>/<esperado> son sintaxis real de Gherkin (columnas de Examples), no huecos.
  Scenario Outline: <comportamiento> según <entrada>
    Given <precondición>
    When se ejercita con <entrada>
    Then el resultado es <esperado>

    Examples:
      | entrada | esperado |
      | vacío   | ...      |
      | máx     | ...      |
```
## Provides
<!-- Contrato hacia abajo: qué deja disponible para las tareas que dependen de esta
     (su superficie/API/ficheros nuevos). NO un resumen de los `Then` del Gherkin.
     Si nada depende de esta tarea, pon "—". -->
## Definition of Done
- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor  · solo si `features.tdd`
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)  · solo si `features.tdd`
- [ ] Todos los tests en verde
- [ ] Spec cumplida; lo declarado en `Provides` queda disponible para las dependientes
- [ ] Lint / format / typecheck OK
- [ ] Gate de mutation testing superado (Stryker, umbral `break`)  · salvo `features.mutation-gate: false`
- [ ] Gate de `fact-checker`: afirmaciones de la sesión verificadas (INCORRECTO bloquea) — tras mutation, antes de commit/resumen  · no-negociable, sin flag
- [ ] Documentación — tres capas (TSDoc + doc técnica + histórico)  · cada capa según `features.closing-documentation.*`
- [ ] Docs de dev / usuario final + `pnpm changeset` donde aplique
````

> Las líneas de TDD, gate de mutation y documentación se rigen por
> `.claude/task-pipeline.yml` (preset `mode` + flags): una fase desactivada se omite
> de la DoD. Sin el archivo (o en `full`), todas son obligatorias.

La skill `/plan-task` copia estas plantillas (sus ficheros completos `plan.md` /
`task.md`) al crear cada plan/tarea. No las re-inventes por sesión.

## Crear un plan

> La skill `/plan-task` orquesta todo este flujo (plan mode → plan en `pending/` →
> `grilling` → `design-review` → tareas Gherkin → `scenario-coverage` → handoff TDD
> → gate de mutation). Los pasos de abajo son lo que sigue, y lo que haces tú si lo
> conduces a mano.

1. Redacta el plan con la plantilla.
2. Corre la skill `grilling` antes de aprobar para sacar huecos, supuestos ocultos
   e ítems inviables (rama por rama). Itera hasta que el plan sobreviva al interrogatorio.
3. Corre la skill `design-review`: un subagente fresco revisa el plan COMO UN TODO
   (coherencia, tamaño correcto, mantenibilidad, escalabilidad real, reversibilidad).
   Ajusta el plan con los hallazgos.
4. Tras la aprobación del owner: deja el plan en `.claude/plans/pending/<package>/`,
   `status: pending`.
5. Descompón en tareas. Cada tarea cabe en un commit lógico / una sesión.
6. Corre la skill `scenario-coverage`: un subagente QA fresco endurece los escenarios
   Gherkin del set de tareas por dimensiones (fronteras, errores, estado, requisitos
   ausentes…). Incorpora los huecos aceptados.
7. Rellena la sección **Tasks** del plan: lista ordenada y consciente de
   dependencias.

> `grilling` (paso 2) y la aprobación (paso 4) son **no negociables**. `design-review`
> y `scenario-coverage` (pasos 3 y 6) corren por defecto pero admiten un **salto solo en
> planes triviales**: una sola decisión replicada, sin contrato nuevo ni decisión
> arquitectónica (y, para `scenario-coverage`, 1 tarea sin caminos de error reales).
> Lo confirma el owner **una vez por pasada** (aceptar una no arrastra la otra), se
> registra en el Plan change log y caduca si una re-planificación rompe los criterios.
> Nunca un salto silencioso; sin canal para preguntar, la pasada se ejecuta. Los
> criterios completos, con su frontera resuelta por ejemplo, están en la skill `plan-task`.

## Arrancar un plan

1. Mueve el plan a `.claude/plans/active/<package>/`, `status: active`, bump `updated`.
2. Abre la rama de feature **desde la rama de integración** (p.ej. `dev`, nunca
   desde `main`):

   ```bash
   git switch dev
   git pull
   git switch -c plan/<package>/<name-plan>
   ```

   Todas las tareas del plan caen en esta rama. Al cerrar el plan, se mergea a la
   rama de integración por PR.
3. **(Opcional, `features.github-tracking`)** si el plan tiene `issue:`, proyecta el arranque del **padre**:
   campo **Status del Project → `In progress`** (best-effort). El padre **no** recibe label `status:*` ni
   assignee. Si `gh` falla, avisa y sigue; el `status:` del plan **no** se bloquea.

## Arrancar una tarea

1. Comprueba que todas las `depends_on` están en `done`.
2. Mueve la tarea a `.claude/tasks/active/<package>/`, `status: active`, bump `updated`.
3. Abre el session log en `.claude/context/<package>/<task-id>.md` con la primera entrada.
4. **Solo una tarea por plan puede estar `active`** — comparten rama.
5. **(Opcional, `features.github-tracking`)** si la tarea tiene `issue:`, proyecta el arranque a su issue
   (best-effort): campo **Status del Project → `In progress`**, label **`status: in-progress`** (recipe
   add-then-remove) y **assignee** según la clave `assignee` (ver la tabla completa y el recipe en "Cerrar
   una tarea"). Si `gh` falla, avisa y sigue; el cambio de `status:` del `.md` **no** se bloquea.

> Cada tarea es una conversación/sesión nueva. Las sesiones futuras reconstruyen
> el contexto exclusivamente desde el task file + el session log.

## Trabajar una tarea

- TDD obligatorio (si `features.tdd`, default): test que falla primero, luego la implementación mínima, luego refactor. En `legacy`/`docs-only` con `tdd: false`, no se exige.
- SOLID, Clean Code y los patrones que apliquen — no negociable.
- **Documenta sobre la marcha**: todo símbolo público lleva **TSDoc** al escribirlo
  (no al final). La doc nunca es un afterthought.
- Commits en la rama del plan con `<task-id>: <conventional commit>`.

## Cerrar una tarea

Una tarea es `done` solo cuando **todos** los checkboxes de su DoD son ciertos. En
particular:

1. Todos los tests en verde (`pnpm --filter <pkg> test` o repo-wide `pnpm test`).
2. Lint / format / typecheck OK (`pnpm lint`).
3. **Gate de mutation testing superado** (Stryker, `break: 80`) sobre los ficheros
   que tocó la tarea — salvo que `features.mutation-gate` sea `false`. Survivors por
   debajo del umbral = tests/aserciones que faltan (a menudo un escenario Gherkin sin
   assert real) → refuerza los tests hasta matarlos. Ver la skill `/mutation`.
4. **Gate de `fact-checker`** (no-negociable — sin flag que lo desactive, como
   `grilling`/aprobación): **tras** el gate de mutation y **antes** de commit y del
   resumen final, corre `fact-checker` sobre las afirmaciones factuales de la sesión
   (incluida «el gate de mutation pasó»). `INCORRECTO` **bloquea** el cierre hasta
   corregir la afirmación; `NO VERIFICABLE` es un **aviso a reconocer** explícitamente
   (frecuente en repos sin runner de tests), pero no bloquea; `VERIFICADO` pasa. Aplica
   en cualquier preset (`mode`/`features` no lo tocan). Ver la skill `/fact-checker`.
5. **Documentación actualizada** — tres capas (cada una obligatoria salvo que su flag
   en `features.closing-documentation.*` sea `false`), más dev/usuario donde aplique:
   - **TSDoc en el código** (`tsdoc`): cada símbolo público con su comentario
     (intención, params, returns, errores).
   - **Doc técnica / contexto** (`technical-docs`): README del package, `CLAUDE.md`
     del workspace, `.claude/specs/`, ADRs para decisiones de arquitectura.
   - **Histórico de la tarea** (`context-log`): el session log (paso 6).
   - **Dev / usuario final** (donde aplique): onboarding, guías, scripts,
     `.env.example`, mensajes de error, entrada de `pnpm changeset`.

   Si la tarea no tiene superficie de usuario, el session log lo justifica.
6. Session log cerrado con: resumen, decisiones técnicas + porqué, tests corridos +
   resultado, docs actualizadas (rutas + motivo), ficheros/commits, tiempo real,
   follow-ups.
7. Mueve la tarea a `.claude/tasks/completed/<package>/`, `status: done`, rellena
   `actual:`, bump `updated`.
8. Marca el `[x]` en la sección **Tasks** del plan y bump el `updated` del plan.

El session log es append-only y vive solo en `.claude/context/<package>/<task-id>.md`.
Es el registro canónico; no lo dupliques.

> **Proyección de estado a GitHub (opcional — `features.github-tracking`).** Solo si el flag está
> `enabled` **y** la tarea tiene `issue:` (sin `issue:` → ciclo de vida **local puro**, ni un comando
> `gh`; tampoco dispara un `create` — eso es Paso 5.7 de `/plan-task`). One-way, **best-effort**,
> idempotente desde el `.md`. Al cambiar `status:` el estado se proyecta en **dos sitios**: el **campo
> Status del Project** y una **label `status:*`** en la propia issue.
>
> | Transición | Status del Project | label `status:*` | Issue |
> |---|---|---|---|
> | → `active` (arranque) | `In progress` | `status: in-progress` | + assignee (ver clave `assignee`) |
> | → `in-review` | `In review` | `status: in-review` | — |
> | → `blocked` | (queda en `In progress`) | `status: blocked` | — |
> | `blocked` → `active` (desbloqueo) | `In progress` | `status: in-progress` | — |
> | → `done` | `Done` | (retirar `status:*`) | `gh issue close` |
> | → `cancelled` | `Done` | (retirar `status:*`) | `gh issue close --reason "not planned"` |
> | `done` → `active` (reapertura) | `In progress` | `status: in-progress` | `gh issue reopen` |
>
> **Familia de labels** — `status: in-progress` · `status: blocked` · `status: in-review` (crear con
> `gh label create` si faltan — "ya existe" **no** es fallo; colores sugeridos in-progress `FBCA04`,
> blocked `B60205`, in-review `0E8A16`; descripción `(task-pipeline)`).
>
> **Recipe idempotente (add-then-remove)**: al entrar en un estado, **añade primero** la label nueva y
> **después** retira las demás `status:*` **y la label `blocked` PELADA legacy** (esquema anterior — el
> recipe la migra, o quedaría pegada sin auto-cura). Así un fallo parcial **sobre-etiqueta** (se auto-cura
> en la siguiente transición) en vez de dejar la issue **sin** estado. En `done`/`cancelled` se retiran
> **todas** las `status:*`.
>
> **Assignee** (solo la sub-issue de la tarea; lee la clave `features.github-tracking.assignee`): `@me`
> (default) = identidad `gh` que arranca; un **login** para fijar otro; **`false`** para no asignar. Con
> `gh issue edit --add-assignee` (acumula, no reemplaza; no se desasigna al cerrar). Si el assignee **no
> es colaborador asignable** → avisa y sigue.
>
> **Match del Status case-insensitive** por nombre (`In progress` real ≠ el `In Progress` que a veces
> escriben los docs); si el Project del consumidor **no tiene** la opción esperada → **salta el Status +
> avisa** (la label `status:*` es el fallback visible).
>
> **El body NO se re-vuelca** en transiciones (design-review #3): solo se tocan Status/label/assignee. El
> re-vuelco del body vive en la **re-proyección explícita** (`/doctor` / re-run de `/plan-task`).
>
> **Idempotencia**: cerrar una issue ya cerrada es **no-op** (no error); re-proyectar el estado actual no
> duplica label ni assignee. **Degradación (C3)**: si `gh` falla / sin red / el Project no tiene la opción
> esperada → **avisa y NO bloquees** el cambio de `status:` del `.md` (el `.md` manda; el drift
> `.md`↔label↔Project es **residual aceptado** que se re-alinea al re-proyectar). El cierre de la issue
> **PADRE** del plan y la concurrencia viven en "Cerrar un plan".

## Cerrar un plan

1. Al cerrar la última tarea:
   - Plan → `completed`: mover a `.claude/plans/completed/<package>/`, `status: completed`, bump `updated`.
   - **(Opcional, `features.github-tracking`)** si el plan tiene `issue:`, proyecta el cierre del **padre**:
     campo **Status del Project → `Done`** y `gh issue close` — GitHub **no** la auto-cierra al cerrar las
     sub-issues. El padre **no** lleva label `status:*` ni assignee. Best-effort (C3): si `gh` falla / sin
     red → **avisa y NO bloquees** el cierre del plan (mover a `completed/`, `status:`).
   - Abre PR desde `plan/<package>/<name-plan>` a la rama de integración. **Tests
     en verde y docs al día** son obligatorios antes del merge.
   - Borra la rama tras el merge.
2. La promoción a `main` ocurre en ciclos de release, no al cerrar un plan.
3. Añade una nota retro al plan cerrado: estimación vs. real, sorpresas, dependencias
   no vistas.

## Estados y transiciones

| Entidad | Estados | Notas |
|---|---|---|
| Plan | `pending → active → completed` | `cancelled` desde cualquier estado. |
| Tarea | `pending → active → in-review → done` | `blocked` desde `active` (motivo en el session log) → vuelve a `active` al desbloquear. `cancelled` desde cualquier estado. |

## Re-planificación, bloqueos, cancelación

- Plan obsoleto a mitad → para, corre `grilling` sobre las tareas afectadas,
  ajusta / añade / cancela, registra todo en el **Registro de cambios** del plan.
  No empujes sobre un plan incorrecto.
- Tarea bloqueada → `status: blocked` + motivo en el session log; ninguna otra tarea
  del plan pasa a `active` hasta resolverlo.
- Tarea cancelada → mover a `cancelled/`, `status: cancelled`, registrar motivo.
  Revisa los dependientes.

## Mejora continua

Cada plan cerrado recibe una nota retro comparando `estimate` vs `actual`, las
dependencias no vistas y qué hacer distinto. La calibración mejora estimaciones
futuras y reduce ciclos de `grilling`.
