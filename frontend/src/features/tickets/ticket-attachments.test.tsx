import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import esMessages from "../../../messages/es.json";
import type { components } from "@/types/api";

import { TicketAttachments } from "./ticket-attachments";

type Attachment = components["schemas"]["Attachment"];

function renderWithIntl(ui: React.ReactElement) {
  return render(
    <NextIntlClientProvider locale="es" messages={esMessages} timeZone="Europe/Madrid">
      {ui}
    </NextIntlClientProvider>,
  );
}

const two: Attachment[] = [
  { id: "a1", message_id: "m1", filename: "captura.png", content_type: "image/png", size_bytes: 2048 },
  { id: "a2", message_id: "m1", filename: "log.txt", content_type: "text/plain", size_bytes: 512 },
];

describe("TicketAttachments (solo visualización)", () => {
  it("lista los adjuntos con nombre, tipo, tamaño y enlace de descarga", () => {
    renderWithIntl(<TicketAttachments attachments={two} />);

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);

    const first = items[0]!;
    expect(within(first).getByText("captura.png")).toBeInTheDocument();
    expect(within(first).getByText(/image\/png/)).toBeInTheDocument();
    expect(within(first).getByText("2.0 KB")).toBeInTheDocument();
    const link = within(first).getByRole("link", { name: /descargar/i });
    expect(link).toHaveAttribute("href", expect.stringContaining("/attachments/a1"));
  });

  it("sin adjuntos muestra el estado vacío y NO hay control de subida", () => {
    renderWithIntl(<TicketAttachments attachments={[]} />);

    expect(screen.getByText(/no hay adjuntos/i)).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    // Sin UI de subida en Fase 1.
    expect(screen.queryByRole("button", { name: /subir|adjuntar/i })).not.toBeInTheDocument();
    expect(document.querySelector('input[type="file"]')).toBeNull();
  });
});
