import { describe, expect, it } from "vitest";

import { ticketFixture, tokenFixture } from "@/mocks/fixtures";
import { validateResponse } from "@/mocks/contract/validate";

/**
 * Escenarios Gherkin: «Los tipos se generan desde el contrato → el gate de conformidad pasa»
 * y «Un mock MSW que no cumple el schema falla la validación». La validación runtime con ajv
 * es lo testeable del gate de conformidad.
 */
describe("validateResponse (conformidad de mocks con el contrato)", () => {
  it("acepta un fixture conforme al schema del recurso y no reporta errores", () => {
    const result = validateResponse("Ticket", ticketFixture());

    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("los fixtures base de cada recurso cumplen su schema (gate de conformidad)", () => {
    expect(validateResponse("Ticket", ticketFixture()).valid).toBe(true);
    expect(validateResponse("TokenResponse", tokenFixture()).valid).toBe(true);
  });

  it("rechaza una respuesta que no cumple el schema, señalando el recurso divergente", () => {
    const result = validateResponse("Ticket", ticketFixture({ status: "not-a-status" as never }));

    expect(result.valid).toBe(false);
    expect(result.errors.join(" ")).toContain("Ticket");
  });

  it("el mensaje de error incluye la razón del schema (no solo el recurso)", () => {
    const result = validateResponse("Ticket", ticketFixture({ status: "not-a-status" as never }));

    expect(result.errors.join(" ")).toMatch(/allowed values/);
  });

  it("reporta TODOS los errores ante varias violaciones (allErrors)", () => {
    const result = validateResponse(
      "Ticket",
      ticketFixture({ status: "nope" as never, priority: "nope" as never }),
    );

    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThanOrEqual(2);
  });

  it("rechaza un tipo primitivo equivocado en un campo", () => {
    const result = validateResponse("Ticket", ticketFixture({ subject: 123 as never }));

    expect(result.valid).toBe(false);
  });

  it("lanza (con mensaje propio) para un schema que no existe en el contrato", () => {
    expect(() => validateResponse("NoExiste", {})).toThrow(/desconocido en el contrato: NoExiste/);
  });
});
