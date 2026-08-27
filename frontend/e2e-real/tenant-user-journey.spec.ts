import { expect, test } from "@playwright/test";

import { E2E_USERS } from "./credentials";
import { errorAlert, login } from "./helpers";

/**
 * Ciclo completo de `client-agent` (usuario de tenant, capacidades acotadas: `ticket.create`,
 * `ticket.reply`, `ticket.read`, `kb.read`, `agent.trigger` — sin nada de administración ni
 * aprobaciones) contra el backend real: la nav oculta lo que no puede usar (gating RBAC real, no
 * simulado), crea un ticket de verdad, y confirma que las acciones de estado/asignación (que no tiene)
 * no aparecen en el detalle.
 *
 * No espera el ciclo HITL completo (crear → esperando aprobación → aprobar → publicado) — eso ya lo
 * cubre [[ticket-ai-auto-draft.spec.ts]] con dos contextos de navegador; aquí el foco es el gating por
 * rol y que el alta de ticket funciona de extremo a extremo, no repetir esa aserción con coste real de
 * OpenAI otra vez.
 */
test("client-agent: nav acotada por RBAC + alta de ticket real", async ({ page }) => {
  await login(page, E2E_USERS.clientAgent);
  const nav = page.getByRole("navigation", { name: "Navegación principal" });

  await expect(nav.getByRole("link", { name: "Bandeja" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Base de conocimiento" })).toBeVisible();
  for (const label of ["Aprobaciones", "Panel", "Clientes", "Usuarios", "Roles"]) {
    await expect(nav.getByRole("link", { name: label })).not.toBeVisible();
  }

  await page.getByRole("link", { name: "Nuevo ticket" }).click();
  const subject = `[e2e-real] no veo el botón de publicar ${Date.now()}`;
  await page.getByLabel("Asunto").fill(subject);
  await page.getByLabel("Descripción").fill("El botón de publicar no aparece en el editor.");
  await page.getByRole("button", { name: "Crear ticket" }).click();

  await expect(page).toHaveURL(/\/tickets\/[0-9a-f-]+$/);
  // `ai_auto_draft` (default del tenant `demo`) ya disparó el draft en el servidor — nunca ofrece
  // "Generar borrador" (confirma el descubrimiento del run activo, sin esperar el ciclo completo).
  await expect(page.getByRole("button", { name: "Generar borrador" })).not.toBeVisible();

  // Sin `ticket.transition`/`ticket.assign`: la sección de acciones no ofrece cambiar estado/asignar.
  const actions = page.getByRole("region", { name: "Acciones del ticket" });
  await expect(actions.getByText("Cambiar estado")).not.toBeVisible();
  await expect(actions.getByRole("button", { name: "Asignarme" })).not.toBeVisible();

  // La bandeja (propia del tenant) lista el ticket recién creado.
  await nav.getByRole("link", { name: "Bandeja" }).click();
  await expect(page.getByText(subject)).toBeVisible();

  // KB: búsqueda real (sin asumir que `make ingest` corrió — "sin resultados" es válido).
  await nav.getByRole("link", { name: "Base de conocimiento" }).click();
  await page.getByLabel("Buscar en la base de conocimiento").fill("editor");
  await page.getByRole("button", { name: "Buscar" }).click();
  await expect(errorAlert(page)).not.toBeVisible();

  // Notificaciones: la campana abre su desplegable sin romperse.
  await page.getByRole("button", { name: /Notificaciones/ }).click();
  await expect(
    page.getByRole("list", { name: "Notificaciones" }).or(page.getByText("Sin notificaciones")),
  ).toBeVisible();
});
