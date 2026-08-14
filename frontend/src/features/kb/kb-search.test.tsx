import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { kbSearchHitFixture, meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

import { KbSearch } from "./kb-search";

const SEARCH = `${SESSION_BASE}/api/v1/kb/search`;
const me = meFixture({ capabilities: [{ capability: "kb.read", scope: "tenant" }] });

let lastQuery: Record<string, string> = {};
afterEach(() => {
  lastQuery = {};
});

function serveSearch(items: ReturnType<typeof kbSearchHitFixture>[]) {
  server.use(
    http.get(SEARCH, ({ request }) => {
      lastQuery = Object.fromEntries(new URL(request.url).searchParams);
      return HttpResponse.json({ items, page: 1, page_size: 20, total: items.length });
    }),
  );
}

describe("KbSearch", () => {
  it("búsqueda con resultados: muestra título, dominio y estado", async () => {
    serveSearch([kbSearchHitFixture({ title: "Publicar un sitio", domain: "rendering-and-publishing" })]);
    renderWithSession(<KbSearch />, { me });

    await userEvent.type(screen.getByRole("searchbox", { name: /buscar/i }), "publicar");
    await userEvent.click(screen.getByRole("button", { name: /buscar/i }));

    const link = await screen.findByRole("link", { name: "Publicar un sitio" });
    const item = link.closest("li")!;
    expect(within(item).getByText(/rendering-and-publishing/)).toBeInTheDocument();
    expect(lastQuery.q).toBe("publicar");
  });

  it("búsqueda sin resultados: estado vacío con sugerencia de reformular", async () => {
    serveSearch([]);
    renderWithSession(<KbSearch />, { me });

    await userEvent.type(screen.getByRole("searchbox", { name: /buscar/i }), "zxq");
    await userEvent.click(screen.getByRole("button", { name: /buscar/i }));

    expect(await screen.findByText(/reformula/i)).toBeInTheDocument();
  });

  it("pasa los filtros de dominio/estado a la query", async () => {
    serveSearch([kbSearchHitFixture()]);
    renderWithSession(<KbSearch />, { me });

    await userEvent.type(screen.getByRole("searchbox", { name: /buscar/i }), "algo");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /dominio/i }), "authoring-and-editor");
    await userEvent.click(screen.getByRole("button", { name: /buscar/i }));

    await waitFor(() => expect(lastQuery.domain).toBe("authoring-and-editor"));
    expect(lastQuery.q).toBe("algo");
  });
});
