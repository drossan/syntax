"use client";

import { useState } from "react";

import { problemToUi, type Problem } from "@/lib/api/problem";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import type { components } from "@/types/api";

import { useAuth } from "./auth-context";

type TenantChoice = components["schemas"]["TenantChoice"];

/** Props de {@link TenantSelectionCards}. */
export interface TenantSelectionCardsProps {
  /** `identity_token` del paso 1 del login (reutilizable mientras siga vigente). */
  identityToken: string;
  /** Tenants entre los que elegir. */
  tenants: TenantChoice[];
  /** Se invoca tras completar la sesión con éxito. */
  onSuccess: () => void;
  /** Se invoca al pulsar "Volver a iniciar sesión" (descarta esta elección en curso). */
  onCancel: () => void;
}

/**
 * Pantalla de elección de tenant tras un login con 2+ membresías `active` (sin ruta propia: el
 * `identityToken` no debe viajar por URL/historial). Cada tenant es una card operable por teclado
 * (rol de botón, nombre accesible = nombre del tenant). Mientras resuelve una elección, todas las
 * cards quedan deshabilitadas (sin doble elección ni doble click); un error se informa sobre esta
 * misma pantalla, con un botón "Volver a iniciar sesión" que solo aparece tras ese error.
 */
export function TenantSelectionCards({
  identityToken,
  tenants,
  onSuccess,
  onCancel,
}: TenantSelectionCardsProps) {
  const { selectTenant } = useAuth();
  const [pendingTenantId, setPendingTenantId] = useState<string | null>(null);
  const [error, setError] = useState<Problem | null>(null);
  const busy = pendingTenantId !== null;

  const handleSelect = async (tenantId: string) => {
    setPendingTenantId(tenantId);
    setError(null);
    const result = await selectTenant(identityToken, tenantId);
    setPendingTenantId(null);
    if (result.error) {
      setError(result.error);
      return;
    }
    onSuccess();
  };

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div role="alert" className="flex flex-col gap-2 text-sm text-destructive">
          <p>{problemToUi(error).toast.title}</p>
          <button type="button" onClick={onCancel} className="self-start underline">
            Volver a iniciar sesión
          </button>
        </div>
      ) : null}
      <div className="grid gap-3">
        {tenants.map((tenant) => (
          <button
            key={tenant.id}
            type="button"
            disabled={busy}
            aria-busy={pendingTenantId === tenant.id}
            onClick={() => void handleSelect(tenant.id)}
            className="text-left disabled:opacity-60"
          >
            <Card>
              <CardHeader>
                <CardTitle>{tenant.name}</CardTitle>
              </CardHeader>
            </Card>
          </button>
        ))}
      </div>
    </div>
  );
}
