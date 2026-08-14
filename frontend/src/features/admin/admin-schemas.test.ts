import { describe, expect, it } from "vitest";

import {
  tenantCreateSchema,
  toTenantCreateBody,
  toUserInviteBody,
  userInviteSchema,
} from "./admin-schemas";

describe("tenantCreateSchema / toTenantCreateBody", () => {
  it("exige slug y nombre no vacíos", () => {
    expect(tenantCreateSchema.safeParse({ slug: "", name: "Acme" }).success).toBe(false);
    expect(tenantCreateSchema.safeParse({ slug: "acme", name: "" }).success).toBe(false);
    expect(tenantCreateSchema.safeParse({ slug: "acme", name: "Acme" }).success).toBe(true);
  });

  it("rechaza slug/nombre de solo espacios (se recortan antes de validar)", () => {
    expect(tenantCreateSchema.safeParse({ slug: "   ", name: "Acme" }).success).toBe(false);
    expect(tenantCreateSchema.safeParse({ slug: "acme", name: "   " }).success).toBe(false);
  });

  it("recorta espacios al construir el body", () => {
    expect(toTenantCreateBody({ slug: "  acme  ", name: "  Acme  " })).toStrictEqual({
      slug: "acme",
      name: "Acme",
    });
  });
});

describe("userInviteSchema / toUserInviteBody", () => {
  it("exige email válido y un rol", () => {
    expect(userInviteSchema.safeParse({ email: "no-email", roleId: "r1" }).success).toBe(false);
    expect(userInviteSchema.safeParse({ email: "a@b.io", roleId: "" }).success).toBe(false);
    expect(userInviteSchema.safeParse({ email: "a@b.io", roleId: "r1" }).success).toBe(true);
  });

  it("mapea el rol elegido a un array roles", () => {
    expect(toUserInviteBody({ email: "a@b.io", roleId: "role-9" })).toStrictEqual({
      email: "a@b.io",
      roles: ["role-9"],
    });
  });
});
