import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { server } from "@/mocks/server";
import { ticketPageFixture } from "@/mocks/fixtures";

const BASE = "http://localhost:8000";
const TICKETS = `${BASE}/api/v1/tickets`;

/** Handler que responde 429 (opcionalmente con `Retry-After`) tantas veces como se pida. */
function rateLimited(headers?: Record<string, string>) {
  return http.get(TICKETS, () =>
    HttpResponse.json(
      { type: "about:blank", title: "Rate limited", status: 429 },
      { status: 429, headers },
    ),
  );
}

/**
 * Escenario Outline Gherkin: «Respuesta del cliente según el status» (200/401/429/422)
 * + inyección de token, backoff y aviso de rate-limit. Fuente 1:1 (task frontend-helpdesk-core-02).
 */
describe("createApiClient", () => {
  it("200 → resuelve con datos tipados", async () => {
    server.use(http.get(TICKETS, () => HttpResponse.json(ticketPageFixture())));

    const client = createApiClient({}, BASE);
    const { data, error } = await client.GET("/tickets", {});

    expect(error).toBeUndefined();
    expect(data?.total).toBe(1);
    expect(data?.items[0]?.subject).toBe("No puedo publicar el sitio");
  });

  it("adjunta `Authorization: Bearer <token>` cuando hay access token", async () => {
    let seenAuth: string | null = "unset";
    server.use(
      http.get(TICKETS, ({ request }) => {
        seenAuth = request.headers.get("authorization");
        return HttpResponse.json(ticketPageFixture());
      }),
    );

    const client = createApiClient({ getAccessToken: () => "tok-123" }, BASE);
    await client.GET("/tickets", {});

    expect(seenAuth).toBe("Bearer tok-123");
  });

  it("no adjunta Authorization cuando no hay token", async () => {
    let seenAuth: string | null = "unset";
    server.use(
      http.get(TICKETS, ({ request }) => {
        seenAuth = request.headers.get("authorization");
        return HttpResponse.json(ticketPageFixture());
      }),
    );

    const client = createApiClient({ getAccessToken: () => undefined }, BASE);
    await client.GET("/tickets", {});

    expect(seenAuth).toBeNull();
  });

  it("resuelve la baseUrl desde NEXT_PUBLIC_API_BASE_URL cuando no se pasa explícita", async () => {
    const previous = process.env.NEXT_PUBLIC_API_BASE_URL;
    process.env.NEXT_PUBLIC_API_BASE_URL = BASE;
    try {
      server.use(http.get(TICKETS, () => HttpResponse.json(ticketPageFixture())));

      const client = createApiClient({});
      const { data } = await client.GET("/tickets", {});

      expect(data?.total).toBe(1);
    } finally {
      process.env.NEXT_PUBLIC_API_BASE_URL = previous;
    }
  });

  it("401 → dispara el hook de refresh exactamente una vez", async () => {
    server.use(
      http.get(TICKETS, () =>
        HttpResponse.json(
          { type: "about:blank", title: "No autenticado", status: 401 },
          { status: 401 },
        ),
      ),
    );

    const onUnauthorized = vi.fn();
    const client = createApiClient({ onUnauthorized }, BASE);
    await client.GET("/tickets", {});

    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("no dispara el hook de refresh en respuestas 2xx", async () => {
    server.use(http.get(TICKETS, () => HttpResponse.json(ticketPageFixture())));

    const onUnauthorized = vi.fn();
    const client = createApiClient({ onUnauthorized }, BASE);
    await client.GET("/tickets", {});

    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("un 401 sin hook onUnauthorized no lanza", async () => {
    server.use(
      http.get(TICKETS, () =>
        HttpResponse.json(
          { type: "about:blank", title: "No autenticado", status: 401 },
          { status: 401 },
        ),
      ),
    );

    const client = createApiClient({}, BASE);

    await expect(client.GET("/tickets", {})).resolves.toBeDefined();
  });

  it("429 → aplica backoff, reintenta y expone un aviso de rate-limit", async () => {
    let calls = 0;
    server.use(
      http.get(TICKETS, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(
              { type: "about:blank", title: "Rate limited", status: 429 },
              { status: 429, headers: { "Retry-After": "0" } },
            )
          : HttpResponse.json(ticketPageFixture());
      }),
    );

    const onRateLimit = vi.fn();
    const client = createApiClient({ onRateLimit, delay: () => Promise.resolve() }, BASE);
    const { data } = await client.GET("/tickets", {});

    expect(calls).toBe(2);
    expect(onRateLimit).toHaveBeenCalledTimes(1);
    expect(data?.total).toBe(1);
  });

  it("usa el delay por defecto (sin inyectar) y reintenta con Retry-After 0", async () => {
    let calls = 0;
    server.use(
      http.get(TICKETS, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(
              { type: "about:blank", title: "Rate limited", status: 429 },
              { status: 429, headers: { "Retry-After": "0" } },
            )
          : HttpResponse.json(ticketPageFixture());
      }),
    );

    const client = createApiClient({}, BASE);
    const { data } = await client.GET("/tickets", {});

    expect(calls).toBe(2);
    expect(data?.total).toBe(1);
  });

  it("aplica el `Retry-After` del servidor (segundos → ms) como retardo", async () => {
    const delay = vi.fn(() => Promise.resolve());
    let calls = 0;
    server.use(
      http.get(TICKETS, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(
              { type: "about:blank", title: "Rate limited", status: 429 },
              { status: 429, headers: { "Retry-After": "1" } },
            )
          : HttpResponse.json(ticketPageFixture());
      }),
    );

    const client = createApiClient({ delay }, BASE);
    await client.GET("/tickets", {});

    expect(delay).toHaveBeenCalledWith(1000);
  });

  it("sin `Retry-After` aplica backoff exponencial por intento", async () => {
    const delay = vi.fn(() => Promise.resolve());
    server.use(rateLimited());

    const client = createApiClient({ delay, maxRetries: 2 }, BASE);
    await client.GET("/tickets", {});

    expect(delay.mock.calls).toEqual([[200], [400]]);
  });

  it("429 persistente con maxRetries por defecto → 2 llamadas y devuelve el 429", async () => {
    let calls = 0;
    server.use(
      http.get(TICKETS, () => {
        calls += 1;
        return HttpResponse.json(
          { type: "about:blank", title: "Rate limited", status: 429 },
          { status: 429 },
        );
      }),
    );

    const client = createApiClient({ delay: () => Promise.resolve() }, BASE);
    const { response } = await client.GET("/tickets", {});

    expect(calls).toBe(2);
    expect(response.status).toBe(429);
  });

  it("un 429 sin hook onRateLimit no lanza", async () => {
    server.use(rateLimited());

    const client = createApiClient({ delay: () => Promise.resolve() }, BASE);

    await expect(client.GET("/tickets", {})).resolves.toBeDefined();
  });

  it("422 → el error es un problem+json con errors[] mapeable a campos", async () => {
    server.use(
      http.post(TICKETS, () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Validación fallida",
            status: 422,
            errors: [{ field: "subject", message: "Requerido" }],
          },
          { status: 422 },
        ),
      ),
    );

    const client = createApiClient({}, BASE);
    const { error } = await client.POST("/tickets", { body: { subject: "" } });

    expect(error?.status).toBe(422);
    expect(error?.errors?.[0]?.field).toBe("subject");
  });
});
