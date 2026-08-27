import { expect, test } from "@playwright/test";

import { DEV_PASSWORD, E2E_USERS } from "./credentials";
import { login } from "./helpers";

/**
 * `POST /auth/password/change` existía en el contrato y el backend desde antes de esta tarea, sin
 * NINGÚN componente del front que lo llamara (encontrado auditando password reset/forgot/invite).
 * Cambia la contraseña de verdad, cierra sesión y vuelve a entrar CON LA NUEVA (la única prueba real
 * de que cambió de verdad, no solo que el POST devolvió 204) — y al final la restaura a `DEV_PASSWORD`
 * y confirma esa restauración con un login real, porque `client-viewer@demo.local` es un usuario
 * semilla compartido por el resto de la suite: dejarla a medias rompería specs futuros silenciosamente.
 *
 * Usa `client-viewer` (no `client-agent`/`support-admin`) — el único usuario semilla que ningún otro
 * spec de esta suite toca, para no interferir con sus flujos.
 */
test("cambiar la contraseña propia funciona de verdad (y se restaura al terminar)", async ({
  page,
}) => {
  const TEMP_PASSWORD = `TempE2E${Date.now()}!`;

  await login(page, E2E_USERS.clientViewer);
  await page.getByRole("link", { name: "Cuenta" }).click();

  // Contraseña actual incorrecta → error real del servidor, sin cambiar nada.
  await page.getByLabel("Contraseña actual").fill("esto-no-es-correcto");
  await page.getByLabel("Nueva contraseña", { exact: true }).fill(TEMP_PASSWORD);
  await page.getByLabel("Repite la nueva contraseña").fill(TEMP_PASSWORD);
  await page.getByRole("button", { name: "Cambiar contraseña" }).click();
  await expect(page.getByRole("alert")).toBeVisible();

  // Cambio real con la contraseña actual correcta.
  await page.getByLabel("Contraseña actual").fill(DEV_PASSWORD);
  await page.getByRole("button", { name: "Cambiar contraseña" }).click();
  await expect(page.getByRole("status")).toHaveText("Contraseña actualizada.");

  // Prueba real: cerrar sesión y volver a entrar con la contraseña NUEVA (no solo confiar en el 204).
  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await login(page, { email: E2E_USERS.clientViewer.email, password: TEMP_PASSWORD });

  // Restaura DEV_PASSWORD — obligatorio: este usuario es compartido por toda la suite.
  await page.getByRole("link", { name: "Cuenta" }).click();
  await page.getByLabel("Contraseña actual").fill(TEMP_PASSWORD);
  await page.getByLabel("Nueva contraseña", { exact: true }).fill(DEV_PASSWORD);
  await page.getByLabel("Repite la nueva contraseña").fill(DEV_PASSWORD);
  await page.getByRole("button", { name: "Cambiar contraseña" }).click();
  await expect(page.getByRole("status")).toHaveText("Contraseña actualizada.");

  // Confirma la restauración con un login real — si esto fallara, dejaría el seed roto para el resto
  // de la suite, así que es la aserción más importante del spec, no un extra.
  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await login(page, E2E_USERS.clientViewer);
});
