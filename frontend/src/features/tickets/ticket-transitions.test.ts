import { describe, expect, it } from "vitest";

import { allowedTransitions, isDestructiveTransition } from "./ticket-transitions";

/** Máquina de estados cliente: qué transiciones se ofrecen y cuáles son destructivas. */
describe("allowedTransitions", () => {
  it("desde 'closed' solo ofrece 'reopened' (no ofrece transiciones inválidas)", () => {
    expect(allowedTransitions("closed")).toEqual(["reopened"]);
    expect(allowedTransitions("closed")).not.toContain("open");
    expect(allowedTransitions("closed")).not.toContain("pending");
  });

  it("desde 'open' ofrece pending/resolved/closed y nunca el estado actual", () => {
    const next = allowedTransitions("open");
    expect(next).toContain("pending");
    expect(next).toContain("resolved");
    expect(next).toContain("closed");
    expect(next).not.toContain("open");
  });

  it("desde 'resolved' permite cerrar o reabrir", () => {
    expect(allowedTransitions("resolved")).toEqual(["closed", "reopened"]);
  });

  it("cubre el grafo completo de transiciones (cada estado con su lista exacta)", () => {
    expect(allowedTransitions("new")).toEqual(["open", "pending", "resolved", "closed"]);
    expect(allowedTransitions("open")).toEqual(["pending", "resolved", "closed"]);
    expect(allowedTransitions("pending")).toEqual(["open", "resolved", "closed"]);
    expect(allowedTransitions("resolved")).toEqual(["closed", "reopened"]);
    expect(allowedTransitions("closed")).toEqual(["reopened"]);
    expect(allowedTransitions("reopened")).toEqual(["open", "pending", "resolved", "closed"]);
  });
});

describe("isDestructiveTransition", () => {
  it("cerrar es destructivo (requiere confirmación)", () => {
    expect(isDestructiveTransition("closed")).toBe(true);
  });

  it("solo 'closed' es destructivo; el resto no", () => {
    expect(isDestructiveTransition("closed")).toBe(true);
    for (const status of ["new", "open", "pending", "resolved", "reopened"] as const) {
      expect(isDestructiveTransition(status)).toBe(false);
    }
  });
});
