import { expect, test } from "@playwright/test";

import { E2E_USERS } from "./credentials";
import { login } from "./helpers";

/**
 * Ciclo completo de `tenant.ai_auto_draft` contra el backend real (Postgres + OpenAI real, sin MSW):
 * crear ticket → el servidor dispara el draft SIN que el cliente lo pida → el front lo DESCUBRE al
 * montar (sin clic) → Soporte lo aprueba (otro usuario, otro contexto de navegador) → el mensaje
 * público queda publicado. Esto es exactamente lo que MSW no puede verificar de verdad: MSW resuelve
 * `POST /ai-draft` a `succeeded` al instante, así que nunca ejerce ni el descubrimiento del run
 * activo ni el estado "esperando aprobación humana" (HITL, `auto_approve=false` es el default).
 *
 * Coste real: dispara `agent.trigger` de verdad (clasifica + recupera + puntúa + redacta contra
 * OpenAI) — timeout largo porque esa cadena real puede tardar >10s.
 */
test("ai_auto_draft: crear ticket dispara el draft solo; Soporte lo aprueba; se publica", async ({
  browser,
}) => {
  const agentContext = await browser.newContext();
  const agentPage = await agentContext.newPage();
  await login(agentPage, E2E_USERS.clientAgent);

  await agentPage.goto("/tickets/new");
  const subject = `[e2e-real] activo en mediateca ${Date.now()}`;
  await agentPage.getByLabel("Asunto").fill(subject);
  await agentPage
    .getByLabel("Descripción")
    .fill("¿Cómo subo un activo (imagen) a la mediateca de Griddo?");
  await agentPage.getByRole("button", { name: "Crear ticket" }).click();

  // Redirige a /tickets/{id} — el servidor ya disparó el draft (ai_auto_draft=true, default del
  // tenant `demo`). El panel lo DESCUBRE al montar: nunca debe ofrecer "Generar borrador".
  await expect(agentPage).toHaveURL(/\/tickets\/[0-9a-f-]+$/);
  const ticketUrl = agentPage.url();
  const ticketId = ticketUrl.split("/tickets/")[1];
  await expect(agentPage.getByRole("button", { name: "Generar borrador" })).not.toBeVisible();

  // `demo` tiene `auto_approve=false` → el ciclo real (classify→retrieve→grade→generate→decide)
  // termina en "esperando aprobación", nunca en "listo" directo. Timeout generoso: OpenAI real.
  await expect(agentPage.getByText(/esperando aprobación/i)).toBeVisible({ timeout: 45_000 });

  // Un SEGUNDO usuario (Soporte, otro contexto de navegador) aprueba el draft.
  const supportContext = await browser.newContext();
  const supportPage = await supportContext.newPage();
  await login(supportPage, E2E_USERS.supportAdmin);
  await supportPage.goto("/approvals");

  const ticketLink = supportPage.locator(`a[href="/tickets/${ticketId}"]`);
  await expect(ticketLink).toBeVisible({ timeout: 15_000 });
  const queueItem = supportPage.locator("li").filter({ has: ticketLink });
  await queueItem.getByRole("button", { name: "Aprobar" }).click();

  // El agente (primer contexto) recarga el ticket: el mensaje público real quedó publicado.
  await agentPage.reload();
  await expect(agentPage.getByText(/mediateca/i).first()).toBeVisible({ timeout: 15_000 });

  await agentContext.close();
  await supportContext.close();
});
