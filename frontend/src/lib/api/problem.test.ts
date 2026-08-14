import { describe, expect, it } from "vitest";

import { problemToUi } from "@/lib/api/problem";

/**
 * Escenario Gherkin: «Un envelope de error se traduce a errores de campo y toast».
 * Fuente 1:1 de estos tests (task frontend-helpdesk-core-02).
 */
describe("problemToUi", () => {
  it("mapea errors[] a fieldErrors y usa title/detail localizados como toast", () => {
    const ui = problemToUi({
      type: "about:blank",
      title: "Validación fallida",
      status: 422,
      detail: "Revisa los campos marcados",
      errors: [{ field: "email", message: "Email inválido" }],
    });

    expect(ui.fieldErrors).toEqual({ email: "Email inválido" });
    expect(ui.toast).toEqual({ title: "Validación fallida", detail: "Revisa los campos marcados" });
  });

  it("con varios errors[] mapea cada campo; ignora entradas sin field o message", () => {
    const ui = problemToUi({
      type: "about:blank",
      title: "Error",
      status: 422,
      errors: [
        { field: "email", message: "Requerido" },
        { field: "password", message: "Demasiado corta" },
        { message: "sin campo" },
        { field: "sin_mensaje" },
      ],
    });

    expect(ui.fieldErrors).toEqual({ email: "Requerido", password: "Demasiado corta" });
  });

  it("sin errors[] devuelve fieldErrors vacío", () => {
    const ui = problemToUi({ type: "about:blank", title: "Error interno", status: 500 });

    expect(ui.fieldErrors).toEqual({});
    expect(ui.toast.title).toBe("Error interno");
  });

  it("usa el traductor de fallback cuando el title viene vacío", () => {
    const ui = problemToUi({ type: "about:blank", title: "", status: 500 }, (key) => `t:${key}`);

    expect(ui.toast.title).toBe("t:errors.generic");
  });

  it("sin traductor y con title vacío devuelve title vacío sin lanzar", () => {
    const ui = problemToUi({ type: "about:blank", title: "", status: 500 });

    expect(ui.toast.title).toBe("");
  });

  it("cuando no hay detail el toast no incluye la clave detail", () => {
    const ui = problemToUi({ type: "about:blank", title: "Error", status: 500 });

    expect(ui.toast).not.toHaveProperty("detail");
  });
});
