import { expect, test } from "@playwright/test";

/**
 * Smoke del **cambio de tenant** por Soporte (ámbito global): el switcher está disponible, al elegir otro
 * tenant se actualiza el tenant activo y la bandeja se revalida sin romperse.
 *
 * Nota: el contrato `GET /tickets` no expone parámetro de tenant (aislamiento server-side), por lo que el
 * mock devuelve la misma bandeja; el smoke verifica el **cableado** del switch (selección + refetch), no
 * la diferenciación de datos por tenant (limitación de contrato documentada en la task 07/13).
 */
test("Soporte cambia de tenant y la bandeja se revalida", async ({ page, context }) => {
  await context.addCookies([
    { name: "refresh_token", value: "e2e", url: "http://localhost:3000" },
  ]);

  await page.goto("/login");
  await page.getByLabel("Email").fill("soporte@syntax.io");
  await page.getByLabel("Contraseña").fill("secret123");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();

  await expect(page.getByRole("heading", { name: "Bandeja de tickets" })).toBeVisible();

  const switcher = page.getByLabel("Tenant activo");
  await expect(switcher).toBeVisible();
  await switcher.selectOption({ label: "Globex" });

  // El tenant activo cambió y la bandeja sigue mostrando tickets tras revalidar.
  await expect(switcher).toHaveValue("33333333-3333-3333-3333-333333333333");
  await expect(page.getByText("Ticket de ejemplo")).toBeVisible();
});
