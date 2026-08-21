"use client";

import { useState } from "react";

import { useAuth } from "@/features/auth/auth-context";
import { problemToUi } from "@/lib/api/problem";

import { useTenant } from "./tenant-context";

/**
 * Selector de tenant. Visible para **cualquier** usuario con 2+ membresías `active` (no solo
 * Soporte) — la fuente es `availableTenants` (`auth-context`), no `use-tenants.ts` (que sigue
 * sirviendo a la pantalla de administración). Un cambio de tenant es real (`switchTenant`): mientras
 * resuelve, el `<select>` queda deshabilitado; si falla, vuelve a mostrar el tenant anterior y pinta
 * una alerta accesible — la caché de Query no se limpia hasta confirmar el éxito.
 */
export function TenantSwitcher() {
  const { canSwitchTenant, activeTenantId, setActiveTenant, isSwitchingTenant } = useTenant();
  const { availableTenants } = useAuth();
  const [errorTitle, setErrorTitle] = useState<string | null>(null);

  if (!canSwitchTenant) return null;

  const handleChange = async (tenantId: string) => {
    setErrorTitle(null);
    const result = await setActiveTenant(tenantId);
    if (result.error) {
      setErrorTitle(problemToUi(result.error).toast.title);
    }
  };

  return (
    <div className="flex flex-col gap-1">
      <label className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">Tenant</span>
        <select
          aria-label="Tenant activo"
          value={activeTenantId ?? ""}
          disabled={isSwitchingTenant}
          onChange={(event) => void handleChange(event.target.value)}
          className="rounded-md border px-2 py-1 disabled:opacity-60"
        >
          {availableTenants.map((tenant) => (
            <option key={tenant.id} value={tenant.id}>
              {tenant.name}
            </option>
          ))}
        </select>
      </label>
      {errorTitle ? (
        <p role="alert" className="text-sm text-destructive">
          {errorTitle}
        </p>
      ) : null}
    </div>
  );
}
