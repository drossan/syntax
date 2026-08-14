import { describe, expect, it } from "vitest";

import { approvalsQueryKey, buildApprovalsQuery, DEFAULT_APPROVALS_SORT } from "./approvals-query";

/** Query determinista de la cola de aprobaciones (orden por política de la cola). */
describe("buildApprovalsQuery", () => {
  it("pide solo pendientes con el orden por política (sla_due,confidence) y page 1 por defecto", () => {
    expect(buildApprovalsQuery({})).toStrictEqual({
      page: 1,
      page_size: 20,
      status: "pending",
      sort: DEFAULT_APPROVALS_SORT,
    });
  });

  it("clampa la página a >= 1", () => {
    expect(buildApprovalsQuery({ page: 0 }).page).toBe(1);
    expect(buildApprovalsQuery({ page: 4 }).page).toBe(4);
  });

  it("el orden por defecto es 'sla_due,confidence'", () => {
    expect(DEFAULT_APPROVALS_SORT).toBe("sla_due,confidence");
  });
});

describe("approvalsQueryKey", () => {
  it("es estable para la misma query", () => {
    const q = buildApprovalsQuery({});
    expect(approvalsQueryKey(q)).toEqual(["approvals", q]);
  });
});
