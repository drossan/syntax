import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { kbDocumentFixture, meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

import { KbDocument } from "./kb-document";

const me = meFixture({ capabilities: [{ capability: "kb.read", scope: "tenant" }] });
const UC = "UC-API-081";
const DOC = `${SESSION_BASE}/api/v1/kb/documents/${UC}`;
const DOCS = `${SESSION_BASE}/api/v1/kb/documents`;

describe("KbDocument", () => {
  it("muestra el documento y enlaces a relacionados (mismo dominio, sin incluirse a sí mismo)", async () => {
    server.use(
      http.get(DOC, () =>
        HttpResponse.json(
          kbDocumentFixture({ uc_id: UC, title: "Publicar un sitio", domain: "rendering-and-publishing" }),
        ),
      ),
      http.get(DOCS, () =>
        HttpResponse.json({
          items: [
            kbDocumentFixture({ uc_id: UC, title: "Publicar un sitio" }),
            kbDocumentFixture({ uc_id: "UC-API-090", title: "Configurar el dominio" }),
          ],
          page: 1,
          page_size: 20,
          total: 2,
        }),
      ),
    );

    renderWithSession(<KbDocument ucId={UC} />, { me });

    expect(await screen.findByRole("heading", { name: "Publicar un sitio" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /ver fuente/i })).toHaveAttribute(
      "href",
      "https://docs.syntax.io/UC-API-081",
    );

    const related = await screen.findByRole("navigation", { name: /relacionados/i });
    expect(within(related).getByRole("link", { name: /configurar el dominio/i })).toHaveAttribute(
      "href",
      "/kb/UC-API-090",
    );
    // No se enlaza a sí mismo entre los relacionados.
    expect(within(related).queryByRole("link", { name: /publicar un sitio/i })).not.toBeInTheDocument();
  });

  it("documento inaccesible (404) → no encontrado", async () => {
    server.use(
      http.get(DOC, () =>
        HttpResponse.json({ type: "about:blank", title: "No encontrado", status: 404 }, { status: 404 }),
      ),
      http.get(DOCS, () => HttpResponse.json({ items: [], page: 1, page_size: 20, total: 0 })),
    );

    renderWithSession(<KbDocument ucId={UC} />, { me });

    expect(await screen.findByText(/no se encontró el documento/i)).toBeInTheDocument();
  });
});
