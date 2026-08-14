import { describe, expect, it } from "vitest";

import { buildTicketQuery, DEFAULT_PAGE_SIZE, DEFAULT_SORT, ticketsQueryKey } from "./tickets-query";

/**
 * Construcción determinista de los parámetros de `GET /tickets` y de la queryKey.
 * Escenarios: orden/paginación determinista, filtro por estado, aislamiento de tenant.
 */
describe("buildTicketQuery", () => {
  it("aplica defaults deterministas: page 1, page_size 20, sort -updated_at (sin claves de filtro)", () => {
    // `toStrictEqual` distingue `{status: undefined}` de `{}`: la query no debe llevar filtros vacíos.
    expect(buildTicketQuery({})).toStrictEqual({
      page: 1,
      page_size: DEFAULT_PAGE_SIZE,
      sort: DEFAULT_SORT,
    });
  });

  it("clampa una página menor que 1 a la primera página", () => {
    expect(buildTicketQuery({ page: 0 }).page).toBe(1);
    expect(buildTicketQuery({ page: -5 }).page).toBe(1);
  });

  it("conserva una página válida", () => {
    expect(buildTicketQuery({ page: 3 }).page).toBe(3);
  });

  it("trunca una página fraccionaria al entero inferior (defensa)", () => {
    expect(buildTicketQuery({ page: 2.9 }).page).toBe(2);
  });

  it("incluye los filtros del contrato cuando se proporcionan", () => {
    const query = buildTicketQuery({
      filters: { status: "pending", priority: "high", domain: "authoring-and-editor", assignee_id: "a1" },
    });
    expect(query.status).toBe("pending");
    expect(query.priority).toBe("high");
    expect(query.domain).toBe("authoring-and-editor");
    expect(query.assignee_id).toBe("a1");
  });

  it("omite los filtros ausentes (no envía claves undefined)", () => {
    const query = buildTicketQuery({ filters: { status: "open" } });
    expect(query).not.toHaveProperty("priority");
    expect(query).not.toHaveProperty("domain");
    expect(query).not.toHaveProperty("assignee_id");
  });

  it("nunca emite un parámetro de tenant (el server escopa por sujeto; aislamiento multi-tenant)", () => {
    const query = buildTicketQuery({
      filters: { status: "open" },
      // @ts-expect-error un cliente no puede colar un tenant en la query
      tenant_id: "otro-tenant",
    });
    expect(query).not.toHaveProperty("tenant_id");
    expect(query).not.toHaveProperty("tenant");
  });
});

describe("ticketsQueryKey", () => {
  it("incluye el tenant activo para aislar la caché entre tenants (cross-cutting §3)", () => {
    const query = buildTicketQuery({ filters: { status: "open" } });
    const key = ticketsQueryKey("tenant-a", query);
    expect(key).toEqual(["tickets", "tenant-a", query]);
  });

  it("cambia de key al cambiar de tenant con los mismos filtros", () => {
    const query = buildTicketQuery({});
    expect(ticketsQueryKey("tenant-a", query)).not.toEqual(ticketsQueryKey("tenant-b", query));
  });
});
