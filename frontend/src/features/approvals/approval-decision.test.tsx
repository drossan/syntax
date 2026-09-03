import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { approvalTaskFixture, meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";
import type { components } from "@/types/api";

import { ApprovalDecision } from "./approval-decision";

type ApprovalStatus = components["schemas"]["ApprovalStatus"];

const ID = "55555555-5555-5555-5555-555555555555";
const APPROVE = `${SESSION_BASE}/api/v1/approvals/${ID}/approve`;
const EDIT = `${SESSION_BASE}/api/v1/approvals/${ID}/edit`;
const REJECT = `${SESSION_BASE}/api/v1/approvals/${ID}/reject`;

const me = meFixture({ capabilities: [{ capability: "approval.decide", scope: "global" }] });

let posted: Array<{ url: string; body: unknown }> = [];
afterEach(() => {
  posted = [];
});

function capture(url: string, status: ApprovalStatus) {
  server.use(
    http.post(url, async ({ request }) => {
      posted.push({ url, body: await request.json().catch(() => null) });
      return HttpResponse.json(approvalTaskFixture({ id: ID, status }));
    }),
  );
}

const pending = approvalTaskFixture({
  id: ID,
  status: "pending",
  draft_body: "Respuesta propuesta por IA",
});

describe("ApprovalDecision", () => {
  it("aprobar publica la respuesta (POST approve) y se resuelve", async () => {
    capture(APPROVE, "approved");
    renderWithSession(<ApprovalDecision approval={pending} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /^aprobar$/i }));

    await waitFor(() => expect(posted.map((p) => p.url)).toContain(APPROVE));
  });

  it("editar y aprobar publica el texto editado (POST edit con final_body)", async () => {
    capture(EDIT, "edited");
    renderWithSession(<ApprovalDecision approval={pending} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /editar/i }));
    const textarea = await screen.findByRole("textbox", { name: /texto del borrador/i });
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "Texto revisado por el agente");
    await userEvent.click(screen.getByRole("button", { name: /editar y aprobar/i }));

    await waitFor(() => expect(posted[0]?.url).toBe(EDIT));
    expect(posted[0]?.body).toMatchObject({ final_body: "Texto revisado por el agente" });
  });

  it("rechazar exige nota-al-humano y confirmación antes de enviar", async () => {
    capture(REJECT, "rejected");
    renderWithSession(<ApprovalDecision approval={pending} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /^rechazar$/i }));
    const dialog = await screen.findByRole("alertdialog");

    // Sin nota: confirmar no envía y muestra el error de nota requerida.
    await userEvent.click(within(dialog).getByRole("button", { name: /confirmar rechazo/i }));
    expect(within(dialog).getByText(/nota.*obligatoria/i)).toBeInTheDocument();
    expect(posted).toHaveLength(0);

    // Con nota: se envía el rechazo con la nota.
    await userEvent.type(
      within(dialog).getByRole("textbox", { name: /nota/i }),
      "No procede publicar esto",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: /confirmar rechazo/i }));

    await waitFor(() => expect(posted[0]?.url).toBe(REJECT));
    expect(posted[0]?.body).toMatchObject({ human_note: "No procede publicar esto" });
  });

  it("cancelar la confirmación de rechazo no envía el rechazo", async () => {
    capture(REJECT, "rejected");
    renderWithSession(<ApprovalDecision approval={pending} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /^rechazar$/i }));
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /cancelar/i }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(posted).toHaveLength(0);
  });

  it("un draft ya resuelto no se vuelve a aprobar (idempotencia)", async () => {
    renderWithSession(
      <ApprovalDecision approval={approvalTaskFixture({ id: ID, status: "approved" })} />,
      {
        me,
      },
    );

    expect(await screen.findByText(/ya está resuelta/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^aprobar$/i })).not.toBeInTheDocument();
  });

  it("sin borrador (run fallido) ofrece reintentar/escalar en vez de aprobar", async () => {
    renderWithSession(<ApprovalDecision approval={undefined} />, { me });

    expect(await screen.findByText(/no hay borrador/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^aprobar$/i })).not.toBeInTheDocument();
  });

  it("sin borrador, con onRetry, el botón de reintentar lo invoca", async () => {
    const onRetry = vi.fn();
    renderWithSession(<ApprovalDecision approval={undefined} onRetry={onRetry} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /reintentar/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("el borrador con Markdown se muestra formateado, no como texto literal", async () => {
    const markdown = approvalTaskFixture({
      id: ID,
      status: "pending",
      draft_body:
        "Puedes **publicar el sitio** siguiendo estos pasos:\n\n1. Abre el listado\n2. Pulsa publicar",
    });
    renderWithSession(<ApprovalDecision approval={markdown} />, { me });

    expect(await screen.findByText("publicar el sitio")).toBeInTheDocument();
    expect(screen.getByText("publicar el sitio").tagName).toBe("STRONG");
    expect(screen.getByRole("list").tagName).toBe("OL");
    expect(screen.queryByText(/\*\*publicar el sitio\*\*/)).not.toBeInTheDocument();
  });

  it("el borrador con marcado adversario se muestra como texto inerte, nunca se ejecuta", async () => {
    const adversarial = approvalTaskFixture({
      id: ID,
      status: "pending",
      draft_body: "texto <script>window.__pwned = true;</script> normal",
    });
    renderWithSession(<ApprovalDecision approval={adversarial} />, { me });

    await screen.findByText(/normal/);
    expect(document.querySelector("script")).not.toBeInTheDocument();
  });

  it("el borrador truncado a mitad de sintaxis no rompe el render", async () => {
    const truncated = approvalTaskFixture({
      id: ID,
      status: "pending",
      draft_body: "esto es **negrita a medio cortar sin cerrar",
    });
    renderWithSession(<ApprovalDecision approval={truncated} />, { me });

    expect(await screen.findByText(/negrita a medio cortar/)).toBeInTheDocument();
  });

  it("un borrador vacío o solo con espacios no rompe el render", async () => {
    const blank = approvalTaskFixture({ id: ID, status: "pending", draft_body: "   " });
    renderWithSession(<ApprovalDecision approval={blank} />, { me });

    expect(await screen.findByRole("button", { name: /^aprobar$/i })).toBeInTheDocument();
  });

  it("un borrador sin draft_body (campo ausente) renderiza el blockquote vacío, sin fallback visible", async () => {
    const noBody = approvalTaskFixture({ id: ID, status: "pending" });
    delete (noBody as { draft_body?: string }).draft_body;
    renderWithSession(<ApprovalDecision approval={noBody} />, { me });

    await screen.findByRole("button", { name: /^aprobar$/i });
    expect(document.querySelector("blockquote")?.textContent).toBe("");
  });

  it("un enlace del borrador se abre en pestaña nueva sin arriesgar la sesión", async () => {
    const withLink = approvalTaskFixture({
      id: ID,
      status: "pending",
      draft_body: "[ver más](https://example.com/docs)",
    });
    renderWithSession(<ApprovalDecision approval={withLink} />, { me });

    const link = await screen.findByRole("link", { name: "ver más" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("marcado adversario tecleado al editar el borrador se previsualiza inerte", async () => {
    renderWithSession(<ApprovalDecision approval={pending} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /editar/i }));
    const textarea = await screen.findByRole("textbox", { name: /texto del borrador/i });
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "texto <script>window.__pwned = true;</script> normal");

    const preview = document.querySelector<HTMLElement>(".w-md-editor-preview");
    if (!preview) throw new Error("preview no encontrado");
    expect(await within(preview).findByText(/normal/)).toBeInTheDocument();
    expect(document.querySelector("script")).not.toBeInTheDocument();
  });

  it("una casilla de lista-de-tareas tecleada a mano se desenvuelve a texto plano al editar", async () => {
    renderWithSession(<ApprovalDecision approval={pending} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /editar/i }));
    const textarea = await screen.findByRole("textbox", { name: /texto del borrador/i });
    await userEvent.clear(textarea);
    // userEvent.type interpreta `{`/`[` como inicio de secuencias especiales — se escapan doblando.
    await userEvent.type(textarea, "- [[ ]] paso pendiente");

    const preview = document.querySelector<HTMLElement>(".w-md-editor-preview");
    if (!preview) throw new Error("preview no encontrado");
    expect(await within(preview).findByText(/paso pendiente/)).toBeInTheDocument();
    expect(document.querySelector('input[type="checkbox"]')).not.toBeInTheDocument();
  });

  it("un refresco de la cola en segundo plano no pisa una edición activa del borrador", async () => {
    function Harness() {
      const [current, setCurrent] = useState(pending);
      return (
        <>
          <button type="button" onClick={() => setCurrent({ ...pending })}>
            refrescar
          </button>
          <ApprovalDecision approval={current} />
        </>
      );
    }
    renderWithSession(<Harness />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /editar/i }));
    const textarea = await screen.findByRole("textbox", { name: /texto del borrador/i });
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "cambios en curso, sin guardar todavía");

    // Simula un refresco de la cola en segundo plano: una nueva referencia de `approval`, mismo
    // contenido — el `draftText` local no debe resetearse a `approval.draft_body`.
    await userEvent.click(screen.getByRole("button", { name: /refrescar/i }));

    expect(await screen.findByRole("textbox", { name: /texto del borrador/i })).toHaveValue(
      "cambios en curso, sin guardar todavía",
    );
  });

  it("al montar, el diálogo de rechazo no se muestra hasta pulsar 'Rechazar'", async () => {
    renderWithSession(<ApprovalDecision approval={pending} />, { me });

    await screen.findByRole("button", { name: /^aprobar$/i });
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("al abrir el diálogo de rechazo, el error de nota no se muestra antes de intentar confirmar", async () => {
    renderWithSession(<ApprovalDecision approval={pending} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /^rechazar$/i }));
    const dialog = await screen.findByRole("alertdialog");

    expect(within(dialog).queryByText(/nota.*obligatoria/i)).not.toBeInTheDocument();
  });

  it("tras confirmar el rechazo con éxito, el diálogo se cierra", async () => {
    capture(REJECT, "rejected");
    renderWithSession(<ApprovalDecision approval={pending} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /^rechazar$/i }));
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /nota/i }), "No procede");
    await userEvent.click(within(dialog).getByRole("button", { name: /confirmar rechazo/i }));

    await waitFor(() => expect(posted[0]?.url).toBe(REJECT));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("cancelar el rechazo tras un intento fallido limpia la nota y el error para la próxima apertura", async () => {
    renderWithSession(<ApprovalDecision approval={pending} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /^rechazar$/i }));
    let dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /confirmar rechazo/i }));
    expect(within(dialog).getByText(/nota.*obligatoria/i)).toBeInTheDocument();
    await userEvent.type(within(dialog).getByRole("textbox", { name: /nota/i }), "borrador de nota");
    await userEvent.click(within(dialog).getByRole("button", { name: /cancelar/i }));

    await userEvent.click(await screen.findByRole("button", { name: /^rechazar$/i }));
    dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByRole("textbox", { name: /nota/i })).toHaveValue("");
    expect(within(dialog).queryByText(/nota.*obligatoria/i)).not.toBeInTheDocument();
  });

  it("el diálogo de rechazo expone su título accesible real", async () => {
    renderWithSession(<ApprovalDecision approval={pending} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /^rechazar$/i }));
    const dialog = await screen.findByRole("alertdialog");

    expect(dialog).toHaveAttribute("aria-label", "Rechazar el borrador");
  });

  it("el campo de nota del diálogo de rechazo tiene su etiqueta visible real", async () => {
    renderWithSession(<ApprovalDecision approval={pending} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /^rechazar$/i }));
    const dialog = await screen.findByRole("alertdialog");

    expect(within(dialog).getByText("Nota al humano")).toBeInTheDocument();
  });

  it("al pulsar 'Editar' el editor arranca con el texto real del borrador, no vacío", async () => {
    const withDraft = approvalTaskFixture({
      id: ID,
      status: "pending",
      draft_body: "Texto original del borrador, sin editar todavía",
    });
    renderWithSession(<ApprovalDecision approval={withDraft} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /editar/i }));

    expect(await screen.findByRole("textbox", { name: /texto del borrador/i })).toHaveValue(
      "Texto original del borrador, sin editar todavía",
    );
  });

  it("al pulsar 'Editar' sin draft_body, el editor arranca vacío (no con un valor arbitrario)", async () => {
    const noBody = approvalTaskFixture({ id: ID, status: "pending" });
    delete (noBody as { draft_body?: string }).draft_body;
    renderWithSession(<ApprovalDecision approval={noBody} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /editar/i }));

    expect(await screen.findByRole("textbox", { name: /texto del borrador/i })).toHaveValue("");
  });

  it("en modo edición se muestra la etiqueta real del campo de borrador", async () => {
    renderWithSession(<ApprovalDecision approval={pending} />, { me });

    await userEvent.click(await screen.findByRole("button", { name: /editar/i }));

    expect(await screen.findByText("Texto del borrador")).toBeInTheDocument();
  });
});
