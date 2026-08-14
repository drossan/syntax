import { describe, expect, it } from "vitest";

import { isEmptySummary, totalTickets } from "./analytics";

describe("totalTickets", () => {
  it("suma los conteos por estado", () => {
    expect(totalTickets({ open: 3, pending: 2, closed: 5 })).toBe(10);
  });

  it("sin datos es 0", () => {
    expect(totalTickets({})).toBe(0);
    expect(totalTickets(undefined)).toBe(0);
  });
});

describe("isEmptySummary", () => {
  it("es vacío cuando no hay tickets, ni aprobaciones, ni brechas de SLA", () => {
    expect(
      isEmptySummary({ tickets_by_status: {}, approvals_pending: 0, avg_confidence: null, sla_breaches: 0 }),
    ).toBe(true);
  });

  it("no es vacío si hay tickets", () => {
    expect(
      isEmptySummary({ tickets_by_status: { open: 1 }, approvals_pending: 0, avg_confidence: null, sla_breaches: 0 }),
    ).toBe(false);
  });

  it("no es vacío si hay aprobaciones pendientes o brechas de SLA", () => {
    expect(
      isEmptySummary({ tickets_by_status: {}, approvals_pending: 2, avg_confidence: null, sla_breaches: 0 }),
    ).toBe(false);
    expect(
      isEmptySummary({ tickets_by_status: {}, approvals_pending: 0, avg_confidence: null, sla_breaches: 1 }),
    ).toBe(false);
  });
});
