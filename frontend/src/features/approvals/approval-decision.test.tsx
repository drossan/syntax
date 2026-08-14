import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

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

const pending = approvalTaskFixture({ id: ID, status: "pending", draft_body: "Respuesta propuesta por IA" });

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
    const textarea = screen.getByRole("textbox", { name: /texto del borrador/i });
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
    await userEvent.type(within(dialog).getByRole("textbox", { name: /nota/i }), "No procede publicar esto");
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
    renderWithSession(<ApprovalDecision approval={approvalTaskFixture({ id: ID, status: "approved" })} />, {
      me,
    });

    expect(await screen.findByText(/ya está resuelta/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^aprobar$/i })).not.toBeInTheDocument();
  });

  it("sin borrador (run fallido) ofrece reintentar/escalar en vez de aprobar", async () => {
    renderWithSession(<ApprovalDecision approval={undefined} />, { me });

    expect(await screen.findByText(/no hay borrador/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^aprobar$/i })).not.toBeInTheDocument();
  });
});
