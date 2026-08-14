import { Dashboard } from "@/features/analytics/dashboard";
import { RequireCapability } from "@/features/rbac/can";

/** Panel de métricas del helpdesk. Protegido por `analytics.read`. */
export default function DashboardPage() {
  return (
    <RequireCapability capability="analytics.read">
      <Dashboard />
    </RequireCapability>
  );
}
