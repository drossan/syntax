import { describe, expect, it, vi } from "vitest";

import { SessionManager } from "@/features/auth/session";

/**
 * Escenarios Gherkin: «un access expirado se renueva una sola vez ante peticiones concurrentes»
 * (single-flight) y «reuse-detection cierra la sesión». Fuente 1:1 (task frontend-helpdesk-core-03).
 */
describe("SessionManager", () => {
  it("single-flight: N refresh concurrentes disparan una sola llamada a refreshFn", async () => {
    let resolveRefresh: (token: string | null) => void = () => {};
    const refreshFn = vi.fn(
      () =>
        new Promise<string | null>((resolve) => {
          resolveRefresh = resolve;
        }),
    );
    const session = new SessionManager({ refreshFn });

    const pending = Promise.all([session.refresh(), session.refresh(), session.refresh()]);
    resolveRefresh("new-token");
    const results = await pending;

    expect(refreshFn).toHaveBeenCalledTimes(1);
    expect(results).toEqual([true, true, true]);
    expect(session.token).toBe("new-token");
  });

  it("permite un nuevo refresh una vez terminado el anterior", async () => {
    const refreshFn = vi.fn(async () => "tok");
    const session = new SessionManager({ refreshFn });

    await session.refresh();
    await session.refresh();

    expect(refreshFn).toHaveBeenCalledTimes(2);
  });

  it("reuse-detection: refreshFn nulo → false, token limpiado y onLogout", async () => {
    const onLogout = vi.fn();
    const session = new SessionManager({ refreshFn: async () => null, onLogout });
    session.setToken("stale");

    const ok = await session.refresh();

    expect(ok).toBe(false);
    expect(session.token).toBeNull();
    expect(onLogout).toHaveBeenCalledTimes(1);
  });
});
