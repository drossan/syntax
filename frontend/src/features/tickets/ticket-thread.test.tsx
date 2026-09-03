import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { messageFixture } from "@/mocks/fixtures";
import { renderWithIntl } from "@/test/render-with-intl";

import { TicketThread } from "./ticket-thread";

describe("TicketThread", () => {
  it("sin mensajes muestra el estado vacío", () => {
    renderWithIntl(<TicketThread messages={[]} canSeeInternal />);
    expect(screen.getByText(/aún no hay mensajes/i)).toBeInTheDocument();
  });

  it("una nota interna no aparece para quien no tiene note.internal.read", () => {
    const internal = messageFixture({ id: "a", visibility: "internal", body: "nota interna" });
    renderWithIntl(<TicketThread messages={[internal]} canSeeInternal={false} />);
    expect(screen.queryByText("nota interna")).not.toBeInTheDocument();
  });

  it("una nota interna se marca con la etiqueta 'Interna' para quien sí puede verla", () => {
    const internal = messageFixture({ id: "a", visibility: "internal", body: "nota interna" });
    renderWithIntl(<TicketThread messages={[internal]} canSeeInternal />);
    expect(screen.getByText("Interna")).toBeInTheDocument();
    expect(screen.getByText("nota interna")).toBeInTheDocument();
  });

  it("un mensaje público no muestra la etiqueta 'Interna'", () => {
    const publicMessage = messageFixture({ id: "a", visibility: "public" });
    renderWithIntl(<TicketThread messages={[publicMessage]} canSeeInternal />);
    expect(screen.queryByText("Interna")).not.toBeInTheDocument();
  });

  it("muestra la fecha del mensaje formateada (fecha y hora)", () => {
    const message = messageFixture({ id: "a", created_at: "2026-08-13T10:00:00Z" });
    renderWithIntl(<TicketThread messages={[message]} canSeeInternal />);
    expect(screen.getByText(/13 ago 2026/)).toBeInTheDocument();
    expect(screen.getByText(/\d{1,2}:\d{2}/)).toBeInTheDocument();
  });

  it("un mensaje humano muestra el email de su autor, no el UUID", () => {
    const human = messageFixture({
      id: "a",
      is_ai_draft: false,
      author_id: "33333333-3333-3333-3333-333333333333",
      author_email: "soporte@syntax.local",
    });
    renderWithIntl(<TicketThread messages={[human]} canSeeInternal />);

    expect(screen.getByText("soporte@syntax.local")).toBeInTheDocument();
    expect(screen.queryByText("33333333-3333-3333-3333-333333333333")).not.toBeInTheDocument();
  });

  it("un autor sin email resuelto (usuario eliminado) no muestra el UUID en su lugar", () => {
    const orphaned = messageFixture({
      id: "a",
      is_ai_draft: false,
      author_id: "33333333-3333-3333-3333-333333333333",
      author_email: null,
    });
    renderWithIntl(<TicketThread messages={[orphaned]} canSeeInternal />);

    expect(screen.getByText(/usuario eliminado/i)).toBeInTheDocument();
    expect(screen.queryByText("33333333-3333-3333-3333-333333333333")).not.toBeInTheDocument();
  });

  it("marca un mensaje como borrador IA", () => {
    const draft = messageFixture({ id: "a", is_ai_draft: true, body: "respuesta del agente" });
    renderWithIntl(<TicketThread messages={[draft]} canSeeInternal />);
    expect(screen.getByText("Borrador IA")).toBeInTheDocument();
    expect(screen.getByText("Asistente IA")).toBeInTheDocument();
  });

  it("el cuerpo del mensaje con Markdown se renderiza formateado, no como texto literal", () => {
    const withMarkdown = messageFixture({
      id: "a",
      body: "Puedes **publicar el sitio** siguiendo estos pasos:\n\n1. Abre el listado\n2. Pulsa publicar",
    });
    renderWithIntl(<TicketThread messages={[withMarkdown]} canSeeInternal />);

    expect(screen.getByText("publicar el sitio").tagName).toBe("STRONG");
    expect(document.querySelector("li > div ol")).not.toBeNull();
    expect(screen.queryByText(/\*\*publicar el sitio\*\*/)).not.toBeInTheDocument();
  });

  it("un mensaje con marcado adversario se muestra como texto inerte, nunca se ejecuta", () => {
    const adversarial = messageFixture({
      id: "a",
      body: "texto <script>window.__pwned = true;</script> normal",
    });
    renderWithIntl(<TicketThread messages={[adversarial]} canSeeInternal />);

    expect(screen.getByText(/normal/)).toBeInTheDocument();
    expect(document.querySelector("script")).not.toBeInTheDocument();
  });

  it("el renderizado no distingue autor: un mensaje humano con Markdown se formatea igual que uno de IA", () => {
    const human = messageFixture({
      id: "a",
      is_ai_draft: false,
      body: "esto es *importante*",
    });
    renderWithIntl(<TicketThread messages={[human]} canSeeInternal />);

    expect(screen.getByText("importante").tagName).toBe("EM");
  });

  it("un mensaje humano con guiones o asteriscos casuales se sigue leyendo razonablemente", () => {
    const casual = messageFixture({
      id: "a",
      body: "Gracias - lo reviso hoy mismo y te aviso *en cuanto pueda*",
    });
    renderWithIntl(<TicketThread messages={[casual]} canSeeInternal />);

    expect(screen.getByText(/lo reviso hoy mismo y te aviso/)).toBeInTheDocument();
  });

  it("una imagen embebida se carga sin enviar el Referer al servidor externo", () => {
    const withImage = messageFixture({
      id: "a",
      body: "![captura](https://example.com/x.png)",
    });
    renderWithIntl(<TicketThread messages={[withImage]} canSeeInternal />);

    const img = screen.getByRole("img", { name: "captura" });
    expect(img).toHaveAttribute("referrerpolicy", "no-referrer");
  });

  it("un mensaje sin cuerpo (body ausente) renderiza el cuerpo vacío, sin fallback visible", () => {
    const noBody = messageFixture({ id: "a", author_id: null });
    delete (noBody as { body?: string }).body;
    renderWithIntl(<TicketThread messages={[noBody]} canSeeInternal />);

    expect(screen.getByText("Sistema")).toBeInTheDocument();
    expect(document.querySelector(".mt-1.text-sm")?.textContent).toBe("");
  });

  it("un enlace del mensaje se abre en pestaña nueva sin arriesgar la sesión", () => {
    const withLink = messageFixture({ id: "a", body: "[ver más](https://example.com/docs)" });
    renderWithIntl(<TicketThread messages={[withLink]} canSeeInternal />);

    const link = screen.getByRole("link", { name: "ver más" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("varios mensajes se muestran en orden cronológico", () => {
    const later = messageFixture({ id: "b", body: "segundo", created_at: "2026-08-13T12:00:00Z" });
    const earlier = messageFixture({
      id: "a",
      body: "primero",
      created_at: "2026-08-13T09:00:00Z",
    });
    renderWithIntl(<TicketThread messages={[later, earlier]} canSeeInternal />);

    const items = screen.getAllByRole("listitem");
    expect(within(items[0]!).getByText("primero")).toBeInTheDocument();
    expect(within(items[1]!).getByText("segundo")).toBeInTheDocument();
  });
});
