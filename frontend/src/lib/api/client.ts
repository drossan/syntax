import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "@/types/api";

/**
 * Hooks de comportamiento transversal del cliente API. Todos opcionales: el cliente es
 * usable sin ninguno, y las tareas superiores (auth 03) inyectan el refresh real.
 */
export interface ApiClientHooks {
  /** Devuelve el access token actual (en memoria). */
  getAccessToken?: () => string | null | undefined;
  /** Se dispara ante un 401. Punto de enganche del refresh single-flight (task 03). */
  onUnauthorized?: () => void;
  /** Se dispara ante un 429, con el retardo aplicado en ms (aviso de rate-limit). */
  onRateLimit?: (retryAfterMs: number) => void;
  /** Espera inyectable (los tests pasan una resolución inmediata). */
  delay?: (ms: number) => Promise<void>;
  /** Reintentos máximos ante 429 (default 1). */
  maxRetries?: number;
}

const DEFAULT_MAX_RETRIES = 1;
const DEFAULT_BACKOFF_MS = 200;

/** Lee `Retry-After` (segundos) → ms; `null` si ausente o no numérico. */
function parseRetryAfter(response: Response): number | null {
  const header = response.headers.get("Retry-After");
  if (header === null) return null;
  const seconds = Number(header);
  return Number.isFinite(seconds) ? seconds * 1000 : null;
}

/**
 * `fetch` que reintenta con backoff ante 429 y avisa vía `onRateLimit`. Clona la Request en
 * cada intento para no consumir el body en reintentos de mutaciones.
 */
function createRetryingFetch(hooks: ApiClientHooks): typeof fetch {
  const maxRetries = hooks.maxRetries ?? DEFAULT_MAX_RETRIES;
  const delay = hooks.delay ?? ((ms) => new Promise<void>((resolve) => setTimeout(resolve, ms)));

  return async (input, init) => {
    const base = input instanceof Request ? input : new Request(input as RequestInfo | URL, init);

    for (let attempt = 0; ; attempt += 1) {
      const response = await fetch(base.clone());
      if (response.status !== 429) return response;

      const retryAfterMs = parseRetryAfter(response) ?? DEFAULT_BACKOFF_MS * 2 ** attempt;
      hooks.onRateLimit?.(retryAfterMs);
      if (attempt >= maxRetries) return response;
      await delay(retryAfterMs);
    }
  };
}

/**
 * Crea el cliente HTTP tipado contra el contrato (openapi-fetch). Añade `Authorization: Bearer`
 * cuando hay token, engancha el 401 al refresh y aplica backoff+aviso ante 429.
 *
 * @param hooks Comportamiento transversal (token, 401, 429, delay, reintentos).
 * @param baseUrl Origen de la API (default `NEXT_PUBLIC_API_BASE_URL`). Se le añade `/api/v1`.
 * @returns Cliente openapi-fetch tipado con `paths` del contrato.
 */
export function createApiClient(
  hooks: ApiClientHooks = {},
  baseUrl: string = process.env.NEXT_PUBLIC_API_BASE_URL ?? "",
) {
  const client = createClient<paths>({
    baseUrl: `${baseUrl}/api/v1`,
    fetch: createRetryingFetch(hooks),
    // El refresh viaja en cookie httpOnly → hay que enviar credenciales.
    credentials: "include",
  });

  const middleware: Middleware = {
    onRequest({ request }) {
      const token = hooks.getAccessToken?.();
      if (token) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
      return request;
    },
    onResponse({ response }) {
      if (response.status === 401) {
        hooks.onUnauthorized?.();
      }
      return response;
    },
  };
  client.use(middleware);

  return client;
}
