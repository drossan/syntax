import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";
import type { components } from "@/types/api";

import { TicketAttachments } from "./ticket-attachments";

type Attachment = components["schemas"]["Attachment"];

const two: Attachment[] = [
  {
    id: "a1",
    message_id: "m1",
    filename: "captura.png",
    content_type: "image/png",
    size_bytes: 2048,
  },
  { id: "a2", message_id: "m1", filename: "log.txt", content_type: "text/plain", size_bytes: 512 },
];

/**
 * `TicketAttachments` descarga con el cliente autenticado (`useDownloadAttachment`), no un `<a href>`
 * plano (bug real corregido en la misma tarea: sin el Bearer, el backend real responde 401 — ver
 * `use-attachment-download.ts`). Por eso estos tests necesitan la sesión completa (`renderWithSession`),
 * no solo `NextIntlClientProvider` como antes.
 */
describe("TicketAttachments (descarga autenticada)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lista los adjuntos con nombre, tipo, tamaño y botón de descarga", async () => {
    renderWithSession(<TicketAttachments attachments={two} />);

    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(2);

    const first = items[0]!;
    expect(within(first).getByText("captura.png")).toBeInTheDocument();
    expect(within(first).getByText(/image\/png/)).toBeInTheDocument();
    expect(within(first).getByText("2.0 KB")).toBeInTheDocument();
    expect(within(first).getByRole("button", { name: /descargar/i })).toBeInTheDocument();
  });

  it("descargar pide el binario con el Bearer de la sesión y dispara la descarga del blob", async () => {
    let sawAuthHeader = false;
    server.use(
      http.get(`${SESSION_BASE}/api/v1/messages/m1/attachments/a1`, ({ request }) => {
        sawAuthHeader = request.headers.get("authorization")?.startsWith("Bearer ") ?? false;
        return HttpResponse.arrayBuffer(new TextEncoder().encode("contenido-real").buffer, {
          headers: { "content-type": "image/png" },
        });
      }),
    );
    const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:test");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    renderWithSession(<TicketAttachments attachments={two} />);
    const items = await screen.findAllByRole("listitem");
    await userEvent.click(within(items[0]!).getByRole("button", { name: /descargar/i }));

    await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    expect(sawAuthHeader).toBe(true);
  });

  it("si falla la descarga, avisa junto a ESE adjunto sin romper el resto de la lista", async () => {
    server.use(
      http.get(`${SESSION_BASE}/api/v1/messages/m1/attachments/a1`, () =>
        HttpResponse.json(
          { type: "about:blank", title: "No encontrado", status: 404 },
          { status: 404 },
        ),
      ),
    );
    renderWithSession(<TicketAttachments attachments={two} />);
    const items = await screen.findAllByRole("listitem");
    await userEvent.click(within(items[0]!).getByRole("button", { name: /descargar captura/i }));

    expect(await within(items[0]!).findByRole("alert")).toHaveTextContent(/no se pudo descargar/i);
    expect(within(items[1]!).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("sin adjuntos muestra el estado vacío y NO hay control de subida", async () => {
    renderWithSession(<TicketAttachments attachments={[]} />);

    expect(await screen.findByText(/no hay adjuntos/i)).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /subir|adjuntar/i })).not.toBeInTheDocument();
    expect(document.querySelector('input[type="file"]')).toBeNull();
  });
});
