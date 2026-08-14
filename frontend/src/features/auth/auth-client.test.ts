import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { createAuthClient } from "@/features/auth/auth-client";
import { ticketPageFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";

const BASE = "http://localhost:8000";
const TICKETS = `${BASE}/api/v1/tickets`;
const REFRESH = `${BASE}/api/v1/auth/refresh`;

/**
 * Escenarios Gherkin: single-flight del refresh ante 401 concurrentes + reuse-detection.
 * MSW stateful (el token válido cambia tras el refresh). Fuente 1:1 (task frontend-helpdesk-core-03).
 */
describe("createAuthClient — interceptor 401 con single-flight", () => {
  it("3 peticiones con 401 concurrente → un solo /auth/refresh y todas se reintentan con el nuevo token", async () => {
    const validToken = "fresh";
    let refreshCount = 0;
    server.use(
      http.get(TICKETS, ({ request }) => {
        const auth = request.headers.get("authorization");
        return auth === `Bearer ${validToken}`
          ? HttpResponse.json(ticketPageFixture())
          : HttpResponse.json(
              { type: "about:blank", title: "expirado", status: 401 },
              { status: 401 },
            );
      }),
      http.post(REFRESH, () => {
        refreshCount += 1;
        return HttpResponse.json({ access_token: validToken, token_type: "bearer" });
      }),
    );

    const { client, session } = createAuthClient({ baseUrl: BASE });
    session.setToken("stale");

    const [a, b, c] = await Promise.all([
      client.GET("/tickets", {}),
      client.GET("/tickets", {}),
      client.GET("/tickets", {}),
    ]);

    expect(refreshCount).toBe(1);
    expect(a.data?.total).toBe(1);
    expect(b.data?.total).toBe(1);
    expect(c.data?.total).toBe(1);
  });

  it("con un token válido resuelve sin renovar (no llama a /auth/refresh)", async () => {
    let refreshCount = 0;
    server.use(
      http.get(TICKETS, ({ request }) =>
        request.headers.get("authorization") === "Bearer fresh"
          ? HttpResponse.json(ticketPageFixture())
          : HttpResponse.json({ type: "about:blank", title: "x", status: 401 }, { status: 401 }),
      ),
      http.post(REFRESH, () => {
        refreshCount += 1;
        return HttpResponse.json({ access_token: "fresh", token_type: "bearer" });
      }),
    );

    const { client, session } = createAuthClient({ baseUrl: BASE });
    session.setToken("fresh");

    const { data } = await client.GET("/tickets", {});

    expect(refreshCount).toBe(0);
    expect(data?.total).toBe(1);
  });

  it("reuse-detection: un /auth/refresh 401 dispara onLogout, no reintenta y queda sin autorizar", async () => {
    let ticketCalls = 0;
    server.use(
      http.get(TICKETS, () => {
        ticketCalls += 1;
        return HttpResponse.json(
          { type: "about:blank", title: "expirado", status: 401 },
          { status: 401 },
        );
      }),
      http.post(REFRESH, () =>
        HttpResponse.json({ type: "about:blank", title: "reuse", status: 401 }, { status: 401 }),
      ),
    );

    const onLogout = vi.fn();
    const { client, session } = createAuthClient({ baseUrl: BASE, onLogout });
    session.setToken("stale");

    const { response } = await client.GET("/tickets", {});

    expect(onLogout).toHaveBeenCalledTimes(1);
    expect(response.status).toBe(401);
    expect(session.token).toBeNull();
    expect(ticketCalls).toBe(1); // refresh falló → no se reintenta
  });
});
