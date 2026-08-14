import { UsersAdmin } from "@/features/admin/users-admin";
import { RequireCapability } from "@/features/rbac/can";

/** Administración de usuarios + invitación. Protegida por `user.manage` (acotada al tenant server-side). */
export default function UsersPage() {
  return (
    <RequireCapability capability="user.manage">
      <UsersAdmin />
    </RequireCapability>
  );
}
