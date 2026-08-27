import { expect, test } from "@playwright/test";

import { E2E_USERS } from "./credentials";

/**
 * Login real contra el backend real — verifica lo que MSW no puede: CORS + cookie `refresh_token`
 * cross-origin genuinos (frontend en :3000, backend en :8000) y el hash Argon2 real de
 * `backend/app/infra/db/seed.py`.
 */
test("login real: credenciales correctas llevan a la bandeja", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(E2E_USERS.supportAdmin.email);
  await page.getByLabel("Contraseña").fill(E2E_USERS.supportAdmin.password);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();

  await expect(page.getByRole("heading", { name: "Bandeja de tickets" })).toBeVisible();
});

test("login real: password incorrecta se rechaza con un error visible", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(E2E_USERS.supportAdmin.email);
  await page.getByLabel("Contraseña").fill("password-incorrecta-a-propósito");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();

  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Bandeja de tickets" })).not.toBeVisible();
});
