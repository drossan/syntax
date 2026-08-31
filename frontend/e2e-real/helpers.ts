import { expect, type Page } from "@playwright/test";

/** Login real (contra el backend real) hasta aterrizar en la bandeja — compartido por los specs. */
export async function login(page: Page, user: { email: string; password: string }): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Contraseña").fill(user.password);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page.getByRole("heading", { name: "Bandeja de tickets" })).toBeVisible();
}

/**
 * Alerta de error real de la app — excluye el `role="alert"` que Next.js inyecta SIEMPRE
 * (`#__next-route-announcer__`, el anuncio de cambio de ruta para lectores de pantalla): usar
 * `page.getByRole("alert")` a secas da un falso positivo permanente (reproducido en vivo).
 */
export function errorAlert(page: Page) {
  return page.locator('[role="alert"]:not(#__next-route-announcer__)');
}
