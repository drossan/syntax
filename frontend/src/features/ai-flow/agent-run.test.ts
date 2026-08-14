import { describe, expect, it } from "vitest";

import { draftPollInterval, formatConfidencePercent, isTerminal } from "./agent-run";

/** Lógica del ciclo de draft: terminalidad, intervalo de polling y formato de confianza. */
describe("isTerminal", () => {
  it("succeeded y failed son terminales", () => {
    expect(isTerminal("succeeded")).toBe(true);
    expect(isTerminal("failed")).toBe(true);
  });

  it("queued y running no son terminales", () => {
    expect(isTerminal("queued")).toBe(false);
    expect(isTerminal("running")).toBe(false);
  });

  it("undefined (aún sin datos) no es terminal", () => {
    expect(isTerminal(undefined)).toBe(false);
  });
});

describe("draftPollInterval", () => {
  it("sondea mientras no sea terminal", () => {
    expect(draftPollInterval("running", 2000)).toBe(2000);
    expect(draftPollInterval("queued", 500)).toBe(500);
  });

  it("para el polling (false) cuando el run es terminal", () => {
    expect(draftPollInterval("succeeded", 2000)).toBe(false);
    expect(draftPollInterval("failed", 2000)).toBe(false);
  });
});

describe("formatConfidencePercent", () => {
  it("redondea a porcentaje entero", () => {
    expect(formatConfidencePercent(0.9)).toBe("90");
    expect(formatConfidencePercent(0.876)).toBe("88");
    expect(formatConfidencePercent(1)).toBe("100");
    expect(formatConfidencePercent(0)).toBe("0");
  });

  it("confianza ausente → null", () => {
    expect(formatConfidencePercent(null)).toBeNull();
    expect(formatConfidencePercent(undefined)).toBeNull();
  });
});
