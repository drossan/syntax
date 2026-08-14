import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { kbDocumentFixture, kbSearchHitFixture, meFixture, tokenFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { SESSION_BASE } from "@/test/render-with-session";

import { useKbDocument, useKbRelated, useKbSearch } from "./use-kb";

const API = `${SESSION_BASE}/api/v1`;

function makeWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  server.use(
    http.post(`${API}/auth/refresh`, () => HttpResponse.json(tokenFixture())),
    http.get(`${API}/auth/me`, () => HttpResponse.json(meFixture())),
  );
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <AuthProvider baseUrl={SESSION_BASE}>{children}</AuthProvider>
      </QueryClientProvider>
    );
  };
}

describe("useKbSearch", () => {
  it("no busca sin término (input null): no llama a la API", async () => {
    let calls = 0;
    server.use(
      http.get(`${API}/kb/search`, () => {
        calls += 1;
        return HttpResponse.json({ items: [], page: 1, page_size: 20, total: 0 });
      }),
    );
    const { result } = renderHook(() => useKbSearch(null), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.fetchStatus).toBe("idle"));
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(calls).toBe(0);
    expect(result.current.data).toBeUndefined();
  });

  it("busca con q y filtros, y devuelve los hits", async () => {
    let url = "";
    server.use(
      http.get(`${API}/kb/search`, ({ request }) => {
        url = request.url;
        return HttpResponse.json({ items: [kbSearchHitFixture()], page: 1, page_size: 20, total: 1 });
      }),
    );
    const { result } = renderHook(() => useKbSearch({ q: "publicar", domain: "authoring-and-editor" }), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(1);
    expect(url).toContain("q=publicar");
    expect(url).toContain("domain=authoring-and-editor");
  });

  it("propaga error de la búsqueda", async () => {
    server.use(
      http.get(`${API}/kb/search`, () =>
        HttpResponse.json({ type: "about:blank", title: "boom", status: 500 }, { status: 500 }),
      ),
    );
    const { result } = renderHook(() => useKbSearch({ q: "x" }), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useKbDocument", () => {
  it("carga el documento por uc_id", async () => {
    let url = "";
    server.use(
      http.get(`${API}/kb/documents/:ucId`, ({ request }) => {
        url = request.url;
        return HttpResponse.json(kbDocumentFixture({ uc_id: "UC-9" }));
      }),
    );
    const { result } = renderHook(() => useKbDocument("UC-9"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.uc_id).toBe("UC-9");
    expect(url).toContain("/kb/documents/UC-9");
  });

  it("propaga 404 como error", async () => {
    server.use(
      http.get(`${API}/kb/documents/:ucId`, () =>
        HttpResponse.json({ type: "about:blank", title: "nf", status: 404 }, { status: 404 }),
      ),
    );
    const { result } = renderHook(() => useKbDocument("UC-X"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useKbRelated", () => {
  it("no consulta sin dominio: no llama a la API", async () => {
    let calls = 0;
    server.use(
      http.get(`${API}/kb/documents`, () => {
        calls += 1;
        return HttpResponse.json({ items: [], page: 1, page_size: 20, total: 0 });
      }),
    );
    const { result } = renderHook(() => useKbRelated(undefined, "UC-1"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.fetchStatus).toBe("idle"));
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(calls).toBe(0);
  });

  it("pide por dominio y excluye el documento actual", async () => {
    let url = "";
    server.use(
      http.get(`${API}/kb/documents`, ({ request }) => {
        url = request.url;
        return HttpResponse.json({
          items: [kbDocumentFixture({ uc_id: "UC-1" }), kbDocumentFixture({ uc_id: "UC-2" })],
          page: 1,
          page_size: 20,
          total: 2,
        });
      }),
    );
    const { result } = renderHook(() => useKbRelated("rendering-and-publishing", "UC-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.map((d) => d.uc_id)).toEqual(["UC-2"]);
    expect(url).toContain("domain=rendering-and-publishing");
  });
});
