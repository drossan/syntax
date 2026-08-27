import { expect, test } from "@playwright/test";

import { E2E_USERS } from "./credentials";
import { errorAlert, login } from "./helpers";

/**
 * Ciclo completo de `support-admin` (rol global, TODAS las capacidades) contra el backend real: la
 * navegación entera queda visible (sin gating RBAC de por medio), y las 3 pantallas de administración
 * (`/admin/tenants`, `/admin/users`, `/admin/roles`) funcionan de extremo a extremo — alta de tenant,
 * ajustes por tenant, invitación de usuario y asignación de rol, todo contra Postgres real, no MSW.
 *
 * No dispara `agent.trigger` (no crea tickets) — ver [[tenant-user-journey.spec.ts]] y
 * [[ticket-ai-auto-draft.spec.ts]] para el ciclo IA, que sí tiene coste real de OpenAI.
 *
 * `support-admin` solo tiene membership al tenant `syntax` (seed) → el switcher de tenant no aparece
 * (necesita 2+ membresías activas, ver `tenant-switcher.tsx`) — las capacidades globales
 * (`tenant.manage`/`user.manage`/`role.manage`) no dependen de eso, así que no hace falta para cubrir
 * estas pantallas.
 */
test("support-admin: navegación completa + administración de tenants/usuarios/roles", async ({
  page,
}) => {
  await login(page, E2E_USERS.supportAdmin);
  const nav = page.getByRole("navigation", { name: "Navegación principal" });

  // Rol global con TODAS las capacidades del catálogo → todas las entradas de nav visibles.
  for (const label of [
    "Bandeja",
    "Aprobaciones",
    "Base de conocimiento",
    "Panel",
    "Clientes",
    "Usuarios",
    "Roles",
  ]) {
    await expect(nav.getByRole("link", { name: label })).toBeVisible();
  }

  // Panel de analíticas: carga sin error (datos reales del tenant activo, `syntax`).
  await nav.getByRole("link", { name: "Panel" }).click();
  await expect(page.getByRole("heading", { name: "Panel" })).toBeVisible();
  await expect(errorAlert(page)).not.toBeVisible();

  // Clientes: el listado trae los 2 tenants semilla; el toggle de un ajuste persiste de verdad
  // (round-trip PATCH → GET), y se revierte al valor original para no dejar efecto en otros specs
  // (p.ej. `tenant-user-journey.spec.ts` da por hecho `ai_auto_draft=true` en `demo`).
  await nav.getByRole("link", { name: "Clientes" }).click();
  await expect(page.getByRole("heading", { name: "Clientes" })).toBeVisible();
  const demoRow = page.locator("li").filter({ hasText: "Demo Tenant" });
  await expect(demoRow).toBeVisible();
  const autoApprove = demoRow.getByLabel("Auto-aprobar drafts IA");
  const wasChecked = await autoApprove.isChecked();
  await autoApprove.click();
  await expect(autoApprove).toBeChecked({ checked: !wasChecked });
  await autoApprove.click();
  await expect(autoApprove).toBeChecked({ checked: wasChecked });

  // Alta de tenant: slug único (timestamp) — igual que el resto de la suite, no se limpia después
  // (convención ya asumida por `ticket-ai-auto-draft.spec.ts` con sus tickets de prueba).
  const stamp = Date.now();
  await page.getByLabel("Slug").fill(`e2e-real-${stamp}`);
  await page.getByLabel("Nombre").fill(`E2E Real ${stamp}`);
  await page.getByRole("button", { name: "Crear tenant" }).click();
  await expect(page.getByText(`E2E Real ${stamp}`)).toBeVisible();

  // Usuarios: invitación real — el usuario nuevo aparece con estado "Invitado".
  await nav.getByRole("link", { name: "Usuarios" }).click();
  await expect(page.getByRole("heading", { name: "Usuarios" })).toBeVisible();
  const newUserEmail = `e2e-real-${stamp}@syntax.local`;
  await page.getByLabel("Email").fill(newUserEmail);
  await page.getByLabel("Rol").selectOption({ label: "support_viewer" });
  await page.getByRole("button", { name: "Invitar" }).click();
  const userRow = page.getByRole("row", { name: new RegExp(newUserEmail) });
  await expect(userRow).toBeVisible();
  await expect(userRow.getByText("Invitado")).toBeVisible();

  // Roles: catálogo con capacidades reales + asignar un rol adicional al usuario recién invitado (no
  // se toca ningún usuario semilla — evita corromper las asunciones RBAC de otros specs).
  await nav.getByRole("link", { name: "Roles" }).click();
  await expect(page.getByRole("heading", { name: "Roles y capacidades" })).toBeVisible();
  await expect(page.getByText("ticket.read").first()).toBeVisible();
  const assignSelect = page.getByLabel(`Asignar rol a ${newUserEmail}`);
  await assignSelect.selectOption({ label: "support_agent" });
  const assignRow = assignSelect.locator("xpath=ancestor::div[1]");
  await assignRow.getByRole("button", { name: "Asignar" }).click();

  // Aprobaciones: la cola carga sin error (vacía o no, según lo que otros specs hayan dejado pendiente).
  await nav.getByRole("link", { name: "Aprobaciones" }).click();
  await expect(page.getByRole("heading", { name: "Aprobaciones" })).toBeVisible();
  await expect(errorAlert(page)).not.toBeVisible();

  // KB: búsqueda real (sin asumir que `make ingest` corrió — "sin resultados" es un estado válido).
  await nav.getByRole("link", { name: "Base de conocimiento" }).click();
  await page.getByLabel("Buscar en la base de conocimiento").fill("mediateca");
  await page.getByRole("button", { name: "Buscar" }).click();
  await expect(errorAlert(page)).not.toBeVisible();

  // Notificaciones: la campana abre su desplegable sin romperse.
  await page.getByRole("button", { name: /Notificaciones/ }).click();
  await expect(
    page.getByRole("list", { name: "Notificaciones" }).or(page.getByText("Sin notificaciones")),
  ).toBeVisible();
});
