import { describe, expect, it } from "vitest";

import { isPending, noteProvided } from "./approval-status";

/** Lógica de la decisión: pendiente vs resuelta, y validez de la nota-al-humano. */
describe("isPending", () => {
  it("solo 'pending' es decidible", () => {
    expect(isPending("pending")).toBe(true);
    for (const status of ["approved", "edited", "rejected"] as const) {
      expect(isPending(status)).toBe(false);
    }
  });

  it("undefined no es pendiente", () => {
    expect(isPending(undefined)).toBe(false);
  });
});

describe("noteProvided", () => {
  it("una nota con contenido es válida", () => {
    expect(noteProvided("no aplica al caso")).toBe(true);
  });

  it("vacía o solo espacios no es válida", () => {
    expect(noteProvided("")).toBe(false);
    expect(noteProvided("   ")).toBe(false);
  });
});
