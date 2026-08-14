import { describe, expect, it } from "vitest";

import { hasCapability, type CapabilityEntry } from "@/features/rbac/capabilities";

function context(subjectTenantId: string | null, activeTenantId: string | null = subjectTenantId) {
  return { subjectTenantId, activeTenantId };
}

/**
 * Escenarios (incl. refuerzos scenario-coverage): fail-closed, ámbito global cross-tenant, ámbito
 * tenant acotado al propio tenant. Task frontend-helpdesk-core-05.
 */
describe("hasCapability", () => {
  it("fail-closed: capacidades no resueltas (null/undefined) → deny", () => {
    expect(hasCapability(null, "ticket.read", { context: context("t1") })).toBe(false);
    expect(hasCapability(undefined, "ticket.read", { context: context("t1") })).toBe(false);
  });

  it("sin la capacidad pedida → deny", () => {
    const caps: CapabilityEntry[] = [{ capability: "ticket.read", scope: "tenant" }];
    expect(hasCapability(caps, "ticket.assign", { context: context("t1") })).toBe(false);
  });

  it("capacidad de ámbito global aplica a cualquier tenant (cross-tenant)", () => {
    const caps: CapabilityEntry[] = [{ capability: "ticket.assign", scope: "global" }];
    expect(
      hasCapability(caps, "ticket.assign", {
        context: context("syntax", "otro-tenant"),
        resourceTenantId: "otro-tenant",
      }),
    ).toBe(true);
  });

  it("capacidad de ámbito tenant aplica dentro del propio tenant", () => {
    const caps: CapabilityEntry[] = [{ capability: "ticket.assign", scope: "tenant" }];
    expect(hasCapability(caps, "ticket.assign", { context: context("t1") })).toBe(true);
  });

  it("capacidad de ámbito tenant NO aplica a un recurso de otro tenant", () => {
    const caps: CapabilityEntry[] = [{ capability: "ticket.assign", scope: "tenant" }];
    expect(
      hasCapability(caps, "ticket.assign", { context: context("t1"), resourceTenantId: "t2" }),
    ).toBe(false);
  });

  it("capacidad tenant con subjectTenantId nulo → deny", () => {
    const caps: CapabilityEntry[] = [{ capability: "ticket.assign", scope: "tenant" }];
    expect(hasCapability(caps, "ticket.assign", { context: context(null) })).toBe(false);
  });

  it("entrada sin scope → deny", () => {
    const caps: CapabilityEntry[] = [{ capability: "ticket.assign" }];
    expect(hasCapability(caps, "ticket.assign", { context: context("t1") })).toBe(false);
  });
});
