"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { AuthProvider } from "@/features/auth/auth-context";
import { LocaleProvider } from "@/features/shell/locale-provider";
import { ThemeProvider } from "@/features/shell/theme-provider";
import { TenantProvider } from "@/features/tenant/tenant-context";
import { MswGate } from "@/mocks/msw-gate";

/**
 * Providers de cliente que envuelven la app (client-rendered, design-review I1):
 * TanStack Query (data-fetching autenticado) → tema → sesión → tenant → i18n conmutable.
 *
 * @param children Árbol de la aplicación bajo los providers.
 */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <MswGate>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <AuthProvider>
            <TenantProvider>
              <LocaleProvider>{children}</LocaleProvider>
            </TenantProvider>
          </AuthProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </MswGate>
  );
}
