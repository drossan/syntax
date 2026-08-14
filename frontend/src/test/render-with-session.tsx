import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactElement } from "react";

import { AuthProvider } from "@/features/auth/auth-context";
import { LocaleProvider, type Locale } from "@/features/shell/locale-provider";
import { ThemeProvider } from "@/features/shell/theme-provider";
import { TenantProvider } from "@/features/tenant/tenant-context";
import { meFixture, tokenFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import type { components } from "@/types/api";

/** Base URL de la API en tests (MSW intercepta). */
export const SESSION_BASE = "http://localhost:8000";

/**
 * Renderiza `ui` con una sesión autenticada y el stack completo de providers (Query + Theme + Auth +
 * Tenant + Locale). Monta MSW para el bootstrap (`/auth/refresh` + `/auth/me` con el `me` dado). Los
 * tests deben esperar a que la sesión resuelva (`findBy*`) antes de aserciones dependientes de la sesión.
 */
export function renderWithSession(
  ui: ReactElement,
  options?: { me?: components["schemas"]["Me"]; queryClient?: QueryClient; initialLocale?: Locale },
) {
  const me = options?.me ?? meFixture();
  server.use(
    http.post(`${SESSION_BASE}/api/v1/auth/refresh`, () => HttpResponse.json(tokenFixture())),
    http.get(`${SESSION_BASE}/api/v1/auth/me`, () => HttpResponse.json(me)),
  );

  // Sin reintentos en tests: las rutas de error deben resolver de inmediato (no el backoff x3 real).
  const queryClient =
    options?.queryClient ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider baseUrl={SESSION_BASE}>
          <TenantProvider>
            <LocaleProvider initialLocale={options?.initialLocale ?? "es"}>{ui}</LocaleProvider>
          </TenantProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}
