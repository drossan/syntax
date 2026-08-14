import { z } from "zod";

import type { components } from "@/types/api";

type UserInvite = components["schemas"]["UserInvite"];

/** Alta de tenant: `slug` + `name` (contrato `POST /admin/tenants`). */
export const tenantCreateSchema = z.object({
  slug: z.string().trim().min(1, "El slug es obligatorio"),
  name: z.string().trim().min(1, "El nombre es obligatorio"),
});

/** Valores del formulario de alta de tenant. */
export type TenantCreateValues = z.infer<typeof tenantCreateSchema>;

/** Invitación de usuario: email + un rol semilla (contrato `UserInvite` = {email, roles[]}). */
export const userInviteSchema = z.object({
  email: z.string().email("Email no válido"),
  roleId: z.string().min(1, "Elige un rol"),
});

/** Valores del formulario de invitación. */
export type UserInviteValues = z.infer<typeof userInviteSchema>;

/**
 * Construye el body de `POST /admin/tenants` (recorta espacios).
 *
 * @param values Valores validados del formulario.
 */
export function toTenantCreateBody(values: TenantCreateValues) {
  return { slug: values.slug.trim(), name: values.name.trim() };
}

/**
 * Construye el body de `POST /admin/users` mapeando el rol elegido a `roles: [roleId]`.
 *
 * @param values Valores validados del formulario de invitación.
 */
export function toUserInviteBody(values: UserInviteValues): UserInvite {
  return { email: values.email, roles: [values.roleId] };
}
