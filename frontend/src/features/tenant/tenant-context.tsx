"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { useAuth } from "@/features/auth/auth-context";

/** Contexto de tenant activo + capacidad de cambiarlo. */
export interface TenantContextValue {
  /** Tenant del sujeto (su dominio). */
  subjectTenantId: string | null;
  /** Tenant activo: el elegido por Soporte, o el del sujeto. */
  activeTenantId: string | null;
  /** Solo Soporte (alguna capacidad de ámbito `global`) puede cambiar de tenant. */
  canSwitchTenant: boolean;
  /** Cambia el tenant activo (no-op para clientes, fijados a su tenant). */
  setActiveTenant: (tenantId: string) => void;
}

const TenantContext = createContext<TenantContextValue | null>(null);

/**
 * Provee el contexto de tenant. Soporte (ámbito `global`) puede cambiar de tenant; el cliente queda
 * **fijado** a su `tenant_id`. Al cambiar de tenant se resetea la caché de Query (cross-cutting §3:
 * no arrastrar datos del tenant anterior). Debe ir dentro de `AuthProvider` y `QueryClientProvider`.
 */
export function TenantProvider({ children }: { children: ReactNode }) {
  const { user, capabilities } = useAuth();
  const queryClient = useQueryClient();

  const subjectTenantId = user?.tenant_id ?? null;
  const canSwitchTenant = capabilities.some((entry) => entry.scope === "global");
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null);
  const activeTenantId = canSwitchTenant ? (selectedTenantId ?? subjectTenantId) : subjectTenantId;

  const setActiveTenant = useCallback(
    (tenantId: string) => {
      if (!canSwitchTenant) return;
      setSelectedTenantId(tenantId);
      queryClient.clear();
    },
    [canSwitchTenant, queryClient],
  );

  const value = useMemo(
    () => ({ subjectTenantId, activeTenantId, canSwitchTenant, setActiveTenant }),
    [subjectTenantId, activeTenantId, canSwitchTenant, setActiveTenant],
  );

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

/** Accede al contexto de tenant. Lanza fuera de `<TenantProvider>`. */
export function useTenant(): TenantContextValue {
  const ctx = useContext(TenantContext);
  if (!ctx) throw new Error("useTenant debe usarse dentro de <TenantProvider>");
  return ctx;
}
