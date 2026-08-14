import { describe, expect, it } from "vitest";

import { readListState, writeListState } from "./list-state";

describe("readListState", () => {
  it("sin parámetros devuelve la página 1 sin filtros", () => {
    expect(readListState(new URLSearchParams())).toStrictEqual({ page: 1 });
  });

  it("lee página, estado y orden de la query", () => {
    expect(readListState(new URLSearchParams("page=2&status=pending&sort=priority"))).toStrictEqual({
      page: 2,
      status: "pending",
      sort: "priority",
    });
  });

  it("clampa una página inválida a 1", () => {
    expect(readListState(new URLSearchParams("page=0")).page).toBe(1);
    expect(readListState(new URLSearchParams("page=-3")).page).toBe(1);
    expect(readListState(new URLSearchParams("page=abc")).page).toBe(1);
  });
});

describe("writeListState", () => {
  it("omite la página 1 y los filtros vacíos", () => {
    expect(writeListState({ page: 1 })).toBe("");
  });

  it("serializa página, estado y orden", () => {
    expect(writeListState({ page: 2, status: "pending", sort: "priority" })).toBe(
      "page=2&status=pending&sort=priority",
    );
  });

  it("es inverso de readListState (round-trip)", () => {
    const state = { page: 3, status: "open", sort: "updated_at" };
    expect(readListState(new URLSearchParams(writeListState(state)))).toStrictEqual(state);
  });
});
