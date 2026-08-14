import { TenantsAdmin } from "@/features/admin/tenants-admin";
import { RequireCapability } from "@/features/rbac/can";

/** Administración de clientes (tenants). Protegida por `tenant.manage` (solo Soporte). */
export default function TenantsPage() {
  return (
    <RequireCapability capability="tenant.manage">
      <TenantsAdmin />
    </RequireCapability>
  );
}
