---
id: backend-database-foundation-03
package: backend
plan: database-foundation
status: done
priority: 1
depends_on: [backend-database-foundation-02]
estimate: 2.5h
actual: 0.6h
created: 2026-08-15
updated: 2026-08-15
---

# Modelos ORM — identidad/RBAC (8 tablas, sin RLS de tenant)

## Description

Los modelos SQLAlchemy 2 (`Mapped`/`mapped_column`) del grupo **identidad/RBAC**, que es cross-tenant de
sistema y **NO** lleva RLS de fila (`data-model.md` §2/§6): `tenant`, `user`, `capability`, `role`,
`role_capability`, `user_role`, `refresh_session`, `auth_token`. Con sus enums nativos, FKs/cascadas
(`data-model.md` §7) y unicidades. **No** heredan `TenantMixin`. Spec: `data-model.md` (entidades §5, ERD,
enums §3), NFR-003. Guión: `app/infra/db/models/`.

## Spec

- 8 modelos con sus columnas de `data-model.md` §5; PKs UUID; `user.password_hash` (de la primitiva de la
  tarea de security, ya existente); FKs con las cascadas de §7 (RESTRICT en `tenant`).
- Enums nativos: `user_status`, `refresh_session.status` (`active|rotated|revoked`), `auth_token.kind`
  (`password_reset|invitation`), y los que apliquen a este grupo (definirlos como tipos PG nativos).
- Tablas de unión con **PK compuesta**: `role_capability`, `user_role`.
- **Ninguna** de estas 8 tablas lleva `tenant_id`/`TenantMixin` (marca de "sin RLS").
- Registradas en `Base.metadata` (importables por `app.infra.db.models`).

## Fuera de alcance

- Modelos de negocio (04) y KB (05). La migración (06). La lógica de auth (rotación/canje) → plan de auth.

## Scenarios (Gherkin)

<!-- SDD: modelos de infra → Gherkin LOCAL, "sin cambios de spec/CU". Verificación a nivel de metadata (unit). -->

```gherkin
Feature: modelos de identidad y RBAC

  Scenario: las 8 tablas de identidad/RBAC están registradas
    Given la metadata de los modelos
    When se listan las tablas del grupo identidad/RBAC
    Then están las 8 (tenant, user, capability, role, role_capability, user_role, refresh_session, auth_token)

  Scenario: ninguna tabla de identidad lleva RLS de tenant
    Given los modelos de identidad/RBAC
    When se inspeccionan sus columnas
    Then ninguna tiene tenant_id (no son tablas de negocio con RLS)

  Scenario: las tablas de unión tienen PK compuesta
    Given role_capability y user_role
    When se inspecciona su clave primaria
    Then es compuesta (dos columnas FK)

  Scenario Outline: los enums de identidad tienen sus valores
    Given el enum <enum>
    When se inspeccionan sus valores
    Then contiene <valores>

    Examples:
      | enum                  | valores                          |
      | refresh_session.status | active, rotated, revoked        |
      | auth_token.kind        | password_reset, invitation      |

  Scenario: la FK a tenant usa RESTRICT
    Given el modelo user (o los que referencian tenant)
    When se inspecciona la FK a tenant
    Then su on_delete es RESTRICT (data-model §7)

  # ── Endurecido por scenario-coverage ──

  Scenario Outline: las unicidades de negocio están declaradas
    Given el modelo <modelo>
    When se inspeccionan sus constraints de unicidad
    Then existe una única sobre <columnas>

    Examples:
      | modelo          | columnas            |
      | user            | (tenant_id, email)  |
      | role            | (tenant_id, name)   |
      | capability      | (name)              |
      | refresh_session | (token_hash)        |
      | auth_token      | (token_hash)        |

  Scenario: refresh_session tiene parent_id auto-referencial (cadena de rotación)
    Given el modelo refresh_session
    When se inspecciona parent_id
    Then es FK nullable a refresh_session.id

  Scenario Outline: los enums de identidad tienen exactamente su conjunto de valores
    Given el enum <enum>
    When se inspecciona el conjunto de sus valores
    Then es exactamente <valores> (ni más ni menos)

    Examples:
      | enum            | valores                        |
      | user_status     | invited, active, disabled      |
      | tenant_status   | active, disabled               |
      | role_kind       | system, tenant                 |
      | capability_scope | tenant, global                |
```

## Provides

Los 8 modelos ORM de identidad/RBAC en `app.infra.db.models`, disponibles para los modelos de negocio (04,
que referencian `tenant`/`user`), la migración (06) y los repos (08).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario Gherkin tiene al menos un test (8 tablas, sin tenant_id, PK compuesta, enums, RESTRICT).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; el dominio no importa `app.infra`.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation: modelos **declarativos** → mutation N/A documentado (M4 del plan).
- [ ] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de spec/CU — modelos de infra).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings de los modelos/enums; session log.
