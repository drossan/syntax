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
 *
 * También cubre `POST /tickets/{id}/messages` (responder) de extremo a extremo — hasta esta sesión no
 * había NINGÚN componente del front que llamara a ese endpoint pese a que `ticket.reply` ya está en el
 * catálogo RBAC (`backend/app/infra/db/seed.py`) desde antes: sin el reply publicado y visible en el
 * hilo tras recargar, esa desconexión front↔back seguiría sin probarse.
 *
 * Y el ciclo completo de adjuntos: subir con la respuesta, verlo listado tras recargar (antes
 * imposible — el contrato no exponía forma de listar lo ya subido, ampliado esta misma tarea) y
 * descargarlo de verdad. La descarga real es la parte que un test con MSW no puede atrapar: el botón
 * pide el binario con el cliente autenticado (no un `<a href>`, que contra el backend real daba 401 sin
 * el Bearer — bug real, verificado con curl antes de arreglarlo).
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

  // `ticket.reply` (sin `note.internal.write`): responde de verdad, sin selector de visibilidad — el
  // mensaje real queda publicado en el hilo tras recargar (no cacheado en memoria del cliente). Con un
  // adjunto real: sube al mensaje recién creado y queda DESCUBRIBLE tras recargar (antes imposible).
  const replyBody = `[e2e-real] respuesta real ${Date.now()}`;
  await expect(page.getByLabel(/visibilidad/i)).not.toBeVisible();
  await page.getByLabel(/responder/i).fill(replyBody);
  await page.getByLabel(/adjuntar/i).setInputFiles({
    name: "informe.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("contenido real del adjunto"),
  });
  await page.getByRole("button", { name: "Enviar" }).click();
  await expect(page.getByText(replyBody)).toBeVisible();
  await expect(page.getByText("informe.txt")).toBeVisible();
  await page.reload();
  await expect(page.getByText(replyBody)).toBeVisible();
  await expect(page.getByText("informe.txt")).toBeVisible();

  // Descarga real: el botón pide el binario con el Bearer de la sesión (no un `<a href>` plano, que
  // contra el backend real daba 401 — bug real, arreglado en la misma tarea que esta aserción cierra).
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: /descargar informe/i }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("informe.txt");

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
