import type { components } from "@/types/api";

/** Ámbito de una capacidad (`tenant` | `global`), según rbac.md. */
export type CapabilityScope = components["schemas"]["CapabilityScope"];

/** Entrada de capacidad efectiva de la sesión: `{ capability, scope }`. */
export type CapabilityEntry = NonNullable<components["schemas"]["Me"]["capabilities"]>[number];

/** Contexto de tenant para evaluar el ámbito de una capacidad. */
export interface TenantScopeContext {
  /** Tenant del sujeto (su dominio). */
  subjectTenantId: string | null;
  /** Tenant activo (el elegido en el switcher por Soporte, o el del sujeto). */
  activeTenantId: string | null;
}

/**
 * Decide si un sujeto tiene una capacidad respetando el **ámbito** (rbac.md §7). Nunca decide por el
 * nombre del rol. **Fail-closed** (rbac.md §8): capacidades no resueltas (`null`/`undefined`) o ausentes
 * → deny. Una capacidad `global` aplica cross-tenant; una `tenant` solo dentro del tenant del sujeto y
 * sobre recursos de ESE tenant.
 *
 * @param capabilities Capacidades efectivas de la sesión, o `null`/`undefined` si no se resolvieron.
 * @param capability Nombre literal de la capacidad (contrato, p.ej. `ticket.assign`).
 * @param options `resourceTenantId` (tenant del recurso; default = tenant activo) + `context` de tenant.
 * @returns `true` solo si alguna capacidad concuerda y su ámbito cubre el recurso.
 */
export function hasCapability(
  capabilities: CapabilityEntry[] | null | undefined,
  capability: string,
  options: { resourceTenantId?: string | null; context: TenantScopeContext },
): boolean {
  if (!capabilities) return false;

  const { context } = options;
  const resourceTenantId = options.resourceTenantId ?? context.activeTenantId;

  return capabilities.some((entry) => {
    if (entry.capability !== capability) return false;
    if (entry.scope === "global") return true;
    if (entry.scope === "tenant") {
      return context.subjectTenantId !== null && resourceTenantId === context.subjectTenantId;
    }
    return false;
  });
}
