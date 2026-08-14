"use client";

import { useTenant } from "./tenant-context";
import { useTenants } from "./use-tenants";

/**
 * Selector de tenant. Solo visible para Soporte (ámbito global); el cliente no lo ve (queda fijado a
 * su tenant). Cambiar la selección actualiza el tenant activo (y resetea la caché de Query).
 */
export function TenantSwitcher() {
  const { canSwitchTenant, activeTenantId, setActiveTenant } = useTenant();
  const { data: tenants } = useTenants(canSwitchTenant);

  if (!canSwitchTenant) return null;

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Tenant</span>
      <select
        aria-label="Tenant activo"
        value={activeTenantId ?? ""}
        onChange={(event) => setActiveTenant(event.target.value)}
        className="rounded-md border px-2 py-1"
      >
        {(tenants ?? []).map((tenant) => (
          <option key={tenant.id} value={tenant.id}>
            {tenant.name}
          </option>
        ))}
      </select>
    </label>
  );
}
