import type { ReactNode } from "react";

import { AppShell } from "@/features/shell/app-shell";

/** Layout del grupo autenticado `(app)`: envuelve las páginas de feature en el `AppShell`. */
export default function AppLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
