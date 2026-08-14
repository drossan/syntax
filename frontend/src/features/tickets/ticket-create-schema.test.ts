import { describe, expect, it } from "vitest";

import { ticketCreateSchema, toTicketCreateBody } from "./ticket-create-schema";

/** Validación de cliente y construcción del body de `POST /tickets` (contrato `TicketCreate`). */
describe("ticketCreateSchema", () => {
  it("rechaza un asunto vacío con mensaje de campo requerido", () => {
    const result = ticketCreateSchema.safeParse({ subject: "", body: "", priority: "normal" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.message).toMatch(/asunto/i);
      expect(result.error.issues[0]?.path).toEqual(["subject"]);
    }
  });

  it("acepta un formulario válido", () => {
    const result = ticketCreateSchema.safeParse({ subject: "No publica", body: "detalle", priority: "high" });
    expect(result.success).toBe(true);
  });

  it("rechaza un asunto de solo espacios (se recorta antes de validar)", () => {
    expect(ticketCreateSchema.safeParse({ subject: "   ", body: "", priority: "normal" }).success).toBe(
      false,
    );
  });

  it("rechaza una prioridad fuera del enum del contrato", () => {
    expect(ticketCreateSchema.safeParse({ subject: "x", body: "", priority: "ultra" }).success).toBe(false);
  });
});

describe("toTicketCreateBody", () => {
  it("incluye subject y priority", () => {
    expect(toTicketCreateBody({ subject: "Hola", body: "", priority: "normal" })).toStrictEqual({
      subject: "Hola",
      priority: "normal",
    });
  });

  it("incluye body cuando tiene contenido", () => {
    expect(toTicketCreateBody({ subject: "Hola", body: "detalle", priority: "low" })).toStrictEqual({
      subject: "Hola",
      body: "detalle",
      priority: "low",
    });
  });

  it("omite body si solo tiene espacios en blanco", () => {
    expect(toTicketCreateBody({ subject: "Hola", body: "   ", priority: "normal" })).not.toHaveProperty(
      "body",
    );
  });

  it("recorta los espacios del asunto y del body", () => {
    expect(toTicketCreateBody({ subject: "  Hola  ", body: "  detalle  ", priority: "low" })).toStrictEqual(
      { subject: "Hola", body: "detalle", priority: "low" },
    );
  });
});
