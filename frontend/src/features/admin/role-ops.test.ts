import { describe, expect, it } from "vitest";

import { addRole, isSystemRole, removeRole } from "./role-ops";

describe("addRole", () => {
  it("añade un rol nuevo", () => {
    expect(addRole(["a"], "b")).toEqual(["a", "b"]);
  });

  it("no duplica un rol ya presente", () => {
    expect(addRole(["a", "b"], "b")).toEqual(["a", "b"]);
  });

  it("no muta el array original", () => {
    const current = ["a"];
    addRole(current, "b");
    expect(current).toEqual(["a"]);
  });
});

describe("removeRole", () => {
  it("retira un rol presente", () => {
    expect(removeRole(["a", "b"], "a")).toEqual(["b"]);
  });

  it("es no-op si el rol no está", () => {
    expect(removeRole(["a"], "z")).toEqual(["a"]);
  });
});

describe("isSystemRole", () => {
  it("los roles de sistema (semilla) son inmutables", () => {
    expect(isSystemRole("system")).toBe(true);
    expect(isSystemRole("tenant")).toBe(false);
    expect(isSystemRole(undefined)).toBe(false);
  });
});
