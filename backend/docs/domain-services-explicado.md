# Servicios de dominio del backend, explicada para aprender

> Guía didáctica del plan **`domain-services`** (8 tareas). No es la spec (esa vive en `.claude/specs/`)
> ni el histórico (eso son los session logs en `.claude/context/backend/`). Aquí está el **qué**, el
> **por qué** y los **conceptos de Python/backend** que aparecen, contados para alguien que está subiendo
> de nivel. Léela de arriba a abajo una vez; luego úsala como índice.

## 1. La foto grande: ¿qué construimos?

El plan `database-foundation` dejó la capa de datos (tablas, RLS, sesiones, repos genéricos). Este plan
pone **la lógica de negocio de verdad**: los 6 servicios que deciden *qué* pasa (autorizar, autenticar,
mover un ticket de estado, clasificar, aprobar un draft de IA), sin saber *cómo* se persiste nada.

| Tarea | Qué añade | Idea clave que enseña |
|---|---|---|
| 01 | Entidades de identidad (`Tenant`/`User`/`Role`…) + enums | Pydantic v2 como "tipos propios" del dominio |
| 02 | Entidades de negocio + `errors.py` + puertos base | jerarquía de excepciones, `Protocol` como puerto |
| 03 | `rbac_service.authorize` | autorización por capacidad, no por rol; fail-closed |
| 04 | `ticket_service` | máquina de estados con tabla de aristas |
| 05 | `notification_service` | servicio "tonto" a propósito (desacoplado) |
| 06 | `auth_service` | CAS (compare-and-set), reuse-detection, hashing |
| 07 | `classification` | puerto recortado a lo que se usa hoy |
| 08 | `approval_service` | composición de servicios + puerto nuevo |

**Arquitectura hexagonal** = el hilo conductor de todo el plan. El dominio (`app.domain`) contiene la
lógica de negocio pura y **no importa nada de infraestructura** (ni SQLAlchemy, ni un SDK de proveedor).
Habla con el mundo exterior a través de **puertos** (interfaces). Quien implementa esos puertos de verdad
(Postgres, un LLM) son los **adaptadores**, que vienen en planes futuros (11/12/16). Ventaja concreta: en
este plan **no hace falta Docker** — todos los tests son *unit*, con dobles de prueba ("fakes") en vez de
una base de datos real. Comparado con `database-foundation` (que sí necesitaba Postgres), este plan fue
mucho más rápido de verificar.

## 2. Entidades propias del dominio (tareas 01-02)

`app.infra.db.models` (la capa anterior) tiene modelos **SQLAlchemy** — están atados a la tabla, a la
sesión, a cómo se guarda. El dominio necesita sus **propios** tipos, sin esa atadura:

```python
class User(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    status: UserStatus
    password_hash: str | None = None
```

- Son modelos **Pydantic v2** (`BaseModel`), no ORM: no saben nada de tablas, se validan a sí mismos, y
  son la "moneda" que pasa entre servicio y servicio.
- **Enums propios** (`UserStatus`, `TicketStatus`…), no reusados del ORM: mismo valor, pero el dominio no
  depende de `app.infra` (si mañana cambia el ORM, el dominio no se entera). Un test de **drift** compara
  ambos conjuntos de enums valor-a-valor para detectar si se desincronizan.
- Un test de **import estático** (analiza el AST del código, sin ejecutarlo) falla si `app.domain` importa
  `app.infra`/`sqlalchemy` — el guardarraíl automático de la arquitectura hexagonal.

### `app.domain.errors` — una jerarquía con significado

```python
class DomainError(Exception):
    def __init__(self, message, *, code, details=None): ...


class NotFound(DomainError): ...  # el recurso no existe        → 404 futuro


class Conflict(DomainError): ...  # existe pero el estado no cuadra → 409 futuro


class Validation(DomainError): ...  # la entrada no cumple una regla  → 422 futuro


class PortError(DomainError): ...  # un puerto de infra falló (timeout, proveedor caído)
```

Cada servicio lanza una de estas, nunca una excepción "pelada" de Python. Ventaja: el futuro mapeo a
HTTP (planes 11/12) es una **tabla de datos** (`tipo → status code`), no un árbol de `if isinstance`.
`code` es un slug estable (`"auth.invalid_credentials"`) pensado para logs/telemetría, no para el humano.

### `Protocol` — el "puerto" en Python

```python
class UserRepository(Protocol):
    async def get(self, user_id: uuid.UUID) -> User | None: ...
    async def get_by_email(self, tenant_id: uuid.UUID, email: str) -> User | None: ...
```

Un `Protocol` es una interfaz **estructural**: cualquier clase que tenga esos métodos con esa firma "vale"
como `UserRepository`, sin heredar de nada explícitamente (*duck typing* verificado por `mypy`). Los
servicios reciben el puerto **por inyección de constructor** (`__init__(self, users: UserRepository, ...)`)
y los tests le pasan un **fake** — una clase mínima en memoria (un `dict`) que cumple el `Protocol`. Nunca
hace falta una base de datos real para probar la lógica de negocio.

## 3. `rbac_service` — autorizar por capacidad, no por rol (tarea 03)

La tentación obvia es `if user.role == "admin": ...`. Este servicio **no hace eso**:

```python
def authorize(subject: Subject, action: str, resource: Resource) -> Allow | Deny:
    if (action, resource_scope) not in subject.capabilities:
        return Deny(reason=...)
    return Allow()
```

- `subject.capabilities` es un **conjunto de tuplas** `(capability_name, scope)`, ya resuelto server-side
  (roles → capacidades efectivas). El "rol" es solo una forma de *agrupar* capacidades; quien decide es la
  capacidad, no la etiqueta del rol — así un rol custom con menos permisos no puede colarse por el nombre.
- **`Allow`/`Deny(reason)` en vez de lanzar una excepción**: aquí el "no" es un resultado esperado del
  negocio, no un error. Son dos `dataclass(frozen=True)` — el llamante decide qué hacer con la respuesta
  (p. ej. un router futuro la traduce a 403).
- **Fail-closed**: si algo es ambiguo o falta información, la respuesta por defecto es `Deny`, nunca
  `Allow`. En autorización, el error seguro es negar, no permitir.

## 4. `ticket_service` — una máquina de estados como tabla de datos (tarea 04)

```python
_VALID_TRANSITIONS: frozenset[tuple[TicketStatus, TicketStatus]] = frozenset(
    {
        (TicketStatus.new, TicketStatus.open),
        (TicketStatus.open, TicketStatus.pending),
        (TicketStatus.pending, TicketStatus.resolved),
        (TicketStatus.resolved, TicketStatus.closed),
        (TicketStatus.resolved, TicketStatus.reopened),
        (TicketStatus.closed, TicketStatus.reopened),
        (TicketStatus.reopened, TicketStatus.open),
    }
)
```

- Un **`frozenset` de aristas válidas** en vez de una cadena de `if`: añadir/quitar una transición es
  cambiar una línea de datos, no reescribir lógica. `transition()` comprueba `(actual, nueva) in aristas`
  y si no está, lanza `InvalidTransition` (subclase de `Conflict`) — nunca muta el ticket a medias.
- **`reopened` es un estado de reposo real**, no un paso intermedio que "auto-encadena" a `open`: al
  reabrir, el ticket se queda en `reopened` hasta que una transición **separada** lo lleve a `open`. Esto
  se confirmó leyendo el Gherkin literal del caso de uso, no asumiendo el nombre del método.
- **`SlaPolicy` inyectada, nunca inventada**: `sla_due` (cuándo vence el ticket según su prioridad) se
  calcula vía un puerto (`SlaPolicy.due_at(...)`), no con un `timedelta(days=2)` hardcodeado dentro del
  servicio — la política real (duración por prioridad) es un hueco a propósito para un plan futuro (18).
- Toda mutación queda **auditada** (`AuditLogRepository.add(...)`), incluida la reapertura y el CSAT.

## 5. `notification_service` — el valor de un servicio "tonto" (tarea 05)

Este es el más simple del plan a propósito: `emit`/`list_for_user`/`mark_read`/`count_unread`, todos
delegando directo al puerto, sin ninguna regla propia. **Decisión de diseño explícita** (no un olvido):
**desacoplado** de los demás servicios — ningún otro servicio de este plan lo llama. La orquestación
("tras aprobar, notifica") es responsabilidad de una capa *por encima* (el router, plan 11/12), porque
notificar es *best-effort*: si falla, no debería deshacer la operación que la disparó. Aprendizaje: no
todo servicio necesita lógica; a veces el diseño correcto es un *pass-through* fino.

## 6. `auth_service` — el más denso del plan (tarea 06)

### Hashing: dos algoritmos, dos propósitos distintos

```python
hash_password("mi-contraseña")  # Argon2id, salt ALEATORIO → NUNCA buscable por igualdad
hash_token(token)  # SHA-256, DETERMINISTA  → buscable: mismo input, mismo hash
```

Una contraseña se **verifica** (el usuario la escribe cada vez): el salt aleatorio es una ventaja de
seguridad. Un *refresh token* opaco se **busca en la DB por su hash** (`token_hash` es `UNIQUE`): si el
hash no fuera determinista, jamás encontrarías la fila. Por eso hicieron falta **dos** primitivas
distintas — usar Argon2 para el token habría sido, sencillamente, imposible de implementar.

### El patrón CAS (compare-and-set) y por qué importa

```python
async def rotate_if_active(self, token_hash, new_token_hash, now) -> Rotated | Reused:
    """Busca por token_hash y rota SOLO SI la sesión seguía `active` — en una única llamada atómica."""
```

La alternativa ingenua sería `get()` → comprobar en Python → `update()` ("check-then-act"). El problema:
entre el `get` y el `update` puede colarse **otra petición concurrente** (dos pestañas del navegador
renovando el mismo refresh token a la vez) — una **race condition** que ningún test con *fakes* puede
demostrar (un fake no tiene concurrencia real). La solución es subir la atomicidad al **contrato del
puerto**: el adaptador real hace esto con una sola sentencia SQL (`UPDATE ... WHERE status='active'
RETURNING ...`), indivisible a nivel de base de datos. El servicio de dominio nunca hace `if` sobre el
estado antes de mutar — delega la garantía a quien sí puede darla.

### Reuse-detection, explicado con una analogía

Un *refresh token* es de un solo uso: al renovar, se genera uno nuevo y el viejo queda `rotated`. Si
alguien presenta un token **ya rotado** (`Reused`), es la señal de que ese token se filtró y alguien más
lo está usando — la respuesta correcta es revocar **toda la cadena** (`family_id`), no solo esa sesión,
porque no sabes cuál de las dos partes (el legítimo o el atacante) tiene el token bueno. Importante:
**expirado no es lo mismo que reusado** — una sesión que sigue `active` pero cuyo `expires_at` ya pasó
simplemente caducó por el paso del tiempo; ahí no hay reuso y no se dispara la revocación de familia.

### Un bug propio, encontrado por el propio proceso de pruebas

Al endurecer el test de "token inutilizable" (caducado/usado/de otro tipo), los tres casos parametrizados
construían el `AuthToken` con `token_hash="h"` (un string literal) pero llamaban a
`reset_password("plain-h", ...)`. Como `hash_token("plain-h") != "h"`, la búsqueda **nunca encontraba el
token** — los tres casos probaban sin querer la misma rama ("no existe"), no las tres condiciones que
decían probar. Se detectó porque el **mutation testing** (ver §9) dejó sobrevivientes justo en esas
comparaciones — la señal de que "el test pasa" no bastaba, hacía falta que **fallara al mutar la lógica**.

## 7. `classification` — un puerto recortado a lo que existe hoy (tarea 07)

```python
class ChatModel(Protocol):
    async def classify(self, text: str, schema: type[BaseModel]) -> BaseModel: ...
```

El guión original imaginaba un `ChatModel` con `classify`+`generate`+`grade`. Mejor decisión: solo se fija
`classify`, porque es el único método con un **consumidor real hoy** — `generate`/`grade` los diseñará la
tarea 15, cuando exista quien los llame. Fijar una firma sin caller es *adivinar* un contrato; es más
fácil acertar diseñando contra un uso real que contra una intención futura.

`Classification.dominio: KbDomain | None` — `None` es la señal de "no clasificable con confianza"; se
evitó inventar un campo `confidence` numérico que la spec no pedía (FR-023/024 solo piden esa señal
binaria). Y `classify()` **valida la salida**: aunque la firma del puerto diga `-> BaseModel`, un fake (o
un adaptador con bug) podría devolver cualquier cosa — el servicio comprueba `isinstance(result,
Classification)` y rechaza con `Validation` en vez de aceptar ciegamente lo que venga.

## 8. `approval_service` — componer servicios, no reinventar (tarea 08)

`decide()` es el servicio más "orquestador" del plan: no hace nada él solo, **compone** tres piezas ya
existentes:

```python
updated = await self._approvals.decide_if_pending(
    task_id, status.value, final_body, human_note
)  # (1) CAS
if decision in {"approve", "edit"}:
    await self._ticket_service.transition(updated.ticket_id, TicketStatus.pending)  # (2)
await self._agent_runner.resume(updated.agent_run_id, ApprovalOutcome(...))  # (3)
```

- **(1)** reusa el mismo patrón CAS de `auth_service` — aprobar/editar/rechazar una tarea es atómico igual
  que rotar un refresh token: dos aprobaciones a la vez no deben poder "ganar" las dos.
- **(2)** el servicio **inyecta otro servicio de dominio** (`TicketService`), no solo puertos de
  infraestructura — dos piezas de lógica de negocio en la misma capa se pueden componer directamente.
- **Riesgo conocido y documentado, sin arreglar aquí**: si el paso (2) falla (el ticket ya no admite esa
  transición), la tarea de aprobación **ya quedó decidida** en el paso (1) — no hay forma de deshacerlo a
  este nivel (una transacción real que cubra ambos repositorios a la vez es cosa de infraestructura, fuera
  de este plan). Documentarlo explícitamente es mejor que fingir que no puede pasar.
- **Una desviación real del guión, encontrada leyendo el código real**: la tarea decía
  `agent_runner.resume(thread_id, ...)`, asumiendo `approval_task.agent_run.thread_id`. Pero la entidad
  `ApprovalTask` solo tiene `agent_run_id: uuid.UUID` (una referencia, no el objeto embebido) — y la
  propia tarea prohibía inyectar un `AgentRunRepository` para resolverlo. Se cambió el puerto para recibir
  `agent_run_id` directamente; traducirlo al `thread_id` real de LangGraph queda para el adaptador (tarea
  16), que sí tiene esa información. **Moraleja**: un guión escrito antes de que existan las entidades
  reales puede tener huecos — se detectan leyendo el código, no asumiendo que el texto del plan es exacto.
- **Una guardia añadida durante el endurecimiento de mutación**: `decision` es un `Literal["approve",
  "edit", "reject"]` a nivel de *tipo*, pero Python no lo fuerza en *runtime* — un valor inválido que
  llegara sin validar (de un futuro router) habría producido un `KeyError` crudo. Se añadió una
  comprobación explícita que lo convierte en un `Validation` de dominio.

## 9. Cómo se trabaja aquí (TDD + gates + mutation testing)

Mismo ciclo que en `database-foundation`, pero **sin Docker** (todo es *unit* con fakes):

1. **RED**: test que falla primero (confirma que prueba algo real).
2. **GREEN**: código mínimo para pasar.
3. **REFACTOR**: limpiar (en la 06 hubo una reescritura completa tras detectar código muerto propio).
4. **Gates**: `ruff` (lint+formato) · `mypy --strict` · **mutation testing** (`cosmic-ray`) · `/sdd-lint`
   (valida los artefactos de spec: casos de uso bien formados, sin cabos sueltos) · `fact-checker` (un
   agente independiente re-verifica cada afirmación de la sesión contra el código real, no se fía del
   resumen).

**Mutation testing, con un ejemplo concreto de este plan**: cambiar `!=` por `<` en
`user.tenant_id != tenant_id` (login) y comprobar que **algún test falla**. Con UUIDs generados al azar
(`uuid.uuid4()`), a veces ese mutante **sobrevive** — por pura casualidad, el resultado de `<` coincide
con el de `!=` para esos valores concretos. La solución: usar UUIDs **deterministas**
(`uuid.UUID(int=1)`, `uuid.UUID(int=2)`) elegidos a propósito en ambos órdenes, para que la diferencia
entre operadores sea observable siempre, no "a veces". Aparece en 4 de las 8 tareas de este plan.

**Survivors aceptados como quasi-equivalentes**: en varias tareas quedan mutaciones `==`↔`is` sobre
miembros de `Enum` (`UserStatus.active`, `AuthTokenKind.password_reset`…). Los miembros de un `Enum` de
Python son **singletons** — solo existe un objeto por valor — así que `==` e `is` se comportan
*exactamente* igual para ellos; ningún test puede distinguirlos sin acoplarse a un detalle de
implementación irrelevante. Se documentan y se aceptan en vez de perseguir un 0% que no aporta nada.

## 10. Comandos útiles (desde `backend/`)

```bash
make test                          # pytest — todo unit en este plan, no requiere Docker
make lint                          # ruff check + ruff format --check
make typecheck                     # mypy --strict
make mutation                      # cosmic-ray, acotado al fichero de la tarea en cosmic-ray.toml
```

## 11. Para seguir tirando del hilo

- **Por qué** de cada decisión → `.claude/plans/completed/backend/domain-services.md` (Registro de
  cambios: grilling, design-review, scenario-coverage, con el razonamiento completo de cada bifurcación).
- **Qué** exacto (contrato) → `.claude/specs/backend/casos-de-uso/CU-BE-{01,02,03,04,05,06,10}-*.md`.
- **Cómo se hizo cada tarea** (paso a paso, decisiones, tests, supervivientes de mutación) →
  `.claude/context/backend/backend-domain-services-0N.md`.
- **Lo siguiente** (planes 11/12): routers FastAPI + adaptadores reales de estos puertos (repos SQLAlchemy,
  `deps.get_tenant_context`/`require_capability` orquestando `rbac_service`).
