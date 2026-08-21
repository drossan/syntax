"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { useAuth } from "@/features/auth/auth-context";
import type { Problem } from "@/lib/api/problem";

/** Contexto de tenant activo + capacidad de cambiarlo. */
export interface TenantContextValue {
  /**
   * Tenant del sujeto. Tras un switch real, siempre coincide con {@link activeTenantId} (ambos se
   * re-derivan del mismo `Me.active_tenant_id` fresco) — se mantienen como dos campos separados solo
   * porque `use-can.ts`/`capabilities.ts` ya dependen de esta forma, no porque puedan diverger hoy.
   */
  subjectTenantId: string | null;
  /** Tenant activo de la sesión. Ver {@link subjectTenantId}. */
  activeTenantId: string | null;
  /** Cualquier usuario (cliente o Soporte) con 2+ membresías `active` puede cambiar de tenant. */
  canSwitchTenant: boolean;
  /** `true` mientras se resuelve un cambio de tenant (el switcher debe deshabilitarse). */
  isSwitchingTenant: boolean;
  /**
   * Cambia de tenant de verdad (`switchTenant`). En error, devuelve `{ error }` sin tocar la sesión
   * (sigue en el tenant anterior); en éxito, resetea la caché de Query (cross-cutting §3) — nunca de
   * forma optimista. No-op (`{}`) si `canSwitchTenant` es `false`.
   */
  setActiveTenant: (tenantId: string) => Promise<{ error?: Problem }>;
}

const TenantContext = createContext<TenantContextValue | null>(null);

/**
 * Provee el contexto de tenant. Cualquier usuario con 2+ membresías `active` (`availableTenants`)
 * puede cambiar de tenant — ya no solo Soporte. Al cambiar de tenant con éxito se resetea la caché de
 * Query (cross-cutting §3: no arrastrar datos del tenant anterior); un cambio rechazado no toca la
 * caché ni el tenant activo. Debe ir dentro de `AuthProvider` y `QueryClientProvider`.
 */
export function TenantProvider({ children }: { children: ReactNode }) {
  const { sessionTenantId, availableTenants, switchTenant } = useAuth();
  const queryClient = useQueryClient();
  const [isSwitchingTenant, setIsSwitchingTenant] = useState(false);

  const subjectTenantId = sessionTenantId;
  const activeTenantId = sessionTenantId;
  const canSwitchTenant = availableTenants.length > 1;

  const setActiveTenant = useCallback(
    async (tenantId: string): Promise<{ error?: Problem }> => {
      if (!canSwitchTenant) return {};
      setIsSwitchingTenant(true);
      const result = await switchTenant(tenantId);
      setIsSwitchingTenant(false);
      if (!result.error) {
        queryClient.clear();
      }
      return result;
    },
    [canSwitchTenant, queryClient, switchTenant],
  );

  const value = useMemo(
    () => ({
      subjectTenantId,
      activeTenantId,
      canSwitchTenant,
      isSwitchingTenant,
      setActiveTenant,
    }),
    [subjectTenantId, activeTenantId, canSwitchTenant, isSwitchingTenant, setActiveTenant],
  );

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

/** Accede al contexto de tenant. Lanza fuera de `<TenantProvider>`. */
export function useTenant(): TenantContextValue {
  const ctx = useContext(TenantContext);
  if (!ctx) throw new Error("useTenant debe usarse dentro de <TenantProvider>");
  return ctx;
}
