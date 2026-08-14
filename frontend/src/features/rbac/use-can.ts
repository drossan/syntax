import { useAuth } from "@/features/auth/auth-context";
import { useTenant } from "@/features/tenant/tenant-context";

import { hasCapability } from "./capabilities";

/**
 * Hook de autorización en cliente. Deriva de las capacidades de la sesión (03) y del contexto de
 * tenant (05). UX + defensa en profundidad: la API sigue siendo la fuente de verdad.
 *
 * @param capability Nombre de la capacidad requerida.
 * @param options `resourceTenantId` para acotar el ámbito a un recurso de otro tenant.
 */
export function useCan(
  capability: string,
  options?: { resourceTenantId?: string | null },
): boolean {
  const { capabilities } = useAuth();
  const { subjectTenantId, activeTenantId } = useTenant();

  return hasCapability(capabilities, capability, {
    resourceTenantId: options?.resourceTenantId,
    context: { subjectTenantId, activeTenantId },
  });
}
