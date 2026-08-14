import { expect, test } from "@playwright/test";

/**
 * Smoke del **camino dorado** contra la app con MSW (mock stateful): login → crear ticket → generar
 * draft IA → aprobar → ver el mensaje público publicado en el ticket.
 *
 * El `middleware.ts` redirige por presencia de la cookie `refresh_token` (UX, no seguridad); se siembra
 * una cookie dummy — MSW es quien hace la auth real. Toda la navegación tras el `goto` inicial es
 * client-side (clics / back) para preservar el estado en memoria de MSW.
 */
test("login → ticket → draft IA → aprobación → respuesta publicada", async ({ page, context }) => {
  await context.addCookies([
    { name: "refresh_token", value: "e2e", url: "http://localhost:3000" },
  ]);

  await page.goto("/login");
  await page.getByLabel("Email").fill("soporte@syntax.io");
  await page.getByLabel("Contraseña").fill("secret123");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();

  await expect(page.getByRole("heading", { name: "Bandeja de tickets" })).toBeVisible();

  await page.getByRole("link", { name: "Nuevo ticket" }).click();
  await page.getByLabel("Asunto").fill("No puedo publicar el sitio");
  await page.getByLabel("Descripción").fill("Detalle del problema");
  await page.getByRole("button", { name: "Crear ticket" }).click();

  // Detalle del ticket recién creado: generar el draft IA.
  await expect(page.getByRole("button", { name: "Generar borrador" })).toBeVisible();
  await page.getByRole("button", { name: "Generar borrador" }).click();
  await expect(page.getByText("Borrador listo")).toBeVisible();

  // Cola de aprobaciones: aprobar el draft.
  await page.getByRole("link", { name: "Aprobaciones" }).click();
  await expect(page.getByRole("button", { name: "Aprobar" })).toBeVisible();
  await page.getByRole("button", { name: "Aprobar" }).click();

  // Volver (client-side) al detalle: la respuesta aprobada quedó publicada como mensaje público.
  await page.goBack();
  await expect(
    page.getByText("Puedes publicar el sitio desde el panel de despliegue."),
  ).toBeVisible();
});
