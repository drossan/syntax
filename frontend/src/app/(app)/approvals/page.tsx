import { ApprovalsQueue } from "@/features/approvals/approvals-queue";
import { RequireCapability } from "@/features/rbac/can";

/** Cola de aprobaciones (solo Soporte de Syntax). Protegida por `approval.decide`. */
export default function ApprovalsPage() {
  return (
    <RequireCapability capability="approval.decide">
      <ApprovalsQueue />
    </RequireCapability>
  );
}
