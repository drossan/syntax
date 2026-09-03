"use client";

import type { ReactNode } from "react";

import { useCan } from "./use-can";

/**
 * Renderiza `children` solo si el sujeto tiene la capacidad; si no, `fallback` (por defecto nada).
 * Envuelve acciones/enlaces sensibles a permiso.
 */
export function Can({
  capability,
  resourceTenantId,
  fallback = null,
  children,
}: {
  capability: string;
  resourceTenantId?: string | null;
  fallback?: ReactNode;
  children: ReactNode;
}) {
  const allowed = useCan(capability, { resourceTenantId });
  return <>{allowed ? children : fallback}</>;
}

/** Vista de acceso denegado (guard de ruta / reconciliación 403). */
export function AccessDenied() {
  return (
    <div role="alert" className="mx-auto flex max-w-md flex-col gap-2 p-8 text-center">
      <h1 className="text-xl font-semibold tracking-tight">Acceso denegado</h1>
      <p className="text-sm text-muted-foreground">No tienes permiso para ver esta sección.</p>
    </div>
  );
}

/**
 * Guard de ruta por capacidad: renderiza `children` si el sujeto la tiene, o `<AccessDenied />`.
 * Fail-closed: sin capacidades resueltas, deniega.
 */
export function RequireCapability({
  capability,
  children,
}: {
  capability: string;
  children: ReactNode;
}) {
  const allowed = useCan(capability);
  return allowed ? <>{children}</> : <AccessDenied />;
}
