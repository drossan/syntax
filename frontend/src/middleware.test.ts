import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { middleware } from "@/middleware";

function request(path: string, cookie?: string) {
  return new NextRequest(
    new URL(`http://localhost${path}`),
    cookie ? { headers: { cookie } } : undefined,
  );
}

/**
 * Escenario Gherkin: «acceso a ruta protegida sin sesión → redirect a /login». El middleware es
 * redirect UX por presencia de la cookie de refresh (NO control de seguridad). Task 03.
 */
describe("middleware", () => {
  it("ruta protegida sin cookie de refresh → redirect a /login", () => {
    const response = middleware(request("/tickets"));

    expect(response.headers.get("location")).toContain("/login");
  });

  it("ruta protegida con cookie de refresh → continúa", () => {
    const response = middleware(request("/tickets", "refresh_token=abc"));

    expect(response.headers.get("location")).toBeNull();
  });

  it("ruta pública (/login) sin cookie → continúa", () => {
    const response = middleware(request("/login"));

    expect(response.headers.get("location")).toBeNull();
  });

  it("ruta pública (/password/reset) sin cookie → continúa", () => {
    const response = middleware(request("/password/reset"));

    expect(response.headers.get("location")).toBeNull();
  });

  it("el redirect apunta exactamente a /login preservando el origen", () => {
    const response = middleware(request("/tickets/123"));

    expect(response.headers.get("location")).toBe("http://localhost/login");
  });
});
