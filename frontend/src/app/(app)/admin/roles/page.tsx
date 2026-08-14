import { RolesCatalog } from "@/features/admin/roles-catalog";
import { RequireCapability } from "@/features/rbac/can";

/** Roles y capacidades (read-only) + asignación de roles semilla. Protegida por `role.manage`. */
export default function RolesPage() {
  return (
    <RequireCapability capability="role.manage">
      <RolesCatalog />
    </RequireCapability>
  );
}
