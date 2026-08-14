import { type Middleware } from "openapi-fetch";

import { createApiClient } from "@/lib/api/client";

import { SessionManager } from "./session";

/** Opciones para crear el cliente autenticado. */
export interface AuthClientOptions {
  /** Origen de la API (default `NEXT_PUBLIC_API_BASE_URL`). */
  baseUrl?: string;
  /** Se invoca cuando el refresh falla de forma terminal (reuse-detection → logout). */
  onLogout?: () => void;
}

/**
 * Middleware de refresh: ante un 401, dispara `session.refresh()` (single-flight) y, si tiene éxito,
 * reintenta la petición original con el nuevo token. El reintento usa `fetch` crudo (no re-entra en
 * el middleware) para evitar bucles. Nota: reconstruye la Request sin body → los reintentos tras
 * refresh cubren lecturas (GET); las mutaciones deberían re-invocarse desde su capa.
 */
function refreshMiddleware(session: SessionManager): Middleware {
  return {
    async onResponse({ request, response }) {
      if (response.status !== 401) return response;

      const refreshed = await session.refresh();
      if (!refreshed) return response;

      const headers = new Headers(request.headers);
      headers.set("Authorization", `Bearer ${session.token}`);
      return fetch(new Request(request.url, { method: request.method, headers }));
    },
  };
}

/**
 * Crea el cliente HTTP autenticado y su gestor de sesión.
 *
 * - Un cliente "bare" (sin token ni refresh) hace `POST /auth/refresh` para evitar recursión.
 * - El cliente autenticado añade el Bearer y el {@link refreshMiddleware}.
 *
 * @param options `baseUrl` y `onLogout`.
 * @returns `{ client, session }`: el cliente tipado y el {@link SessionManager} para inyectar el token.
 */
export function createAuthClient(options: AuthClientOptions = {}) {
  const { baseUrl, onLogout } = options;

  const bareClient = createApiClient({}, baseUrl);
  const session = new SessionManager({
    refreshFn: async () => {
      const { data } = await bareClient.POST("/auth/refresh", {});
      return data?.access_token ?? null;
    },
    onLogout,
  });

  const client = createApiClient({ getAccessToken: () => session.token }, baseUrl);
  client.use(refreshMiddleware(session));

  return { client, session };
}
