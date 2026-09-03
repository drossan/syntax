import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { useAuth } from "@/features/auth/auth-context";
import { meFixture, messageFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

import { TicketReplyForm } from "./ticket-reply-form";

/** Igual que `can.test.tsx`: confirma que la sesión resolvió DE VERDAD antes de leer "sigue vacío". */
function StatusProbe() {
  return <span>status:{useAuth().status}</span>;
}

const TICKET_ID = "11111111-1111-1111-1111-111111111111";
const MESSAGES = `${SESSION_BASE}/api/v1/tickets/${TICKET_ID}/messages`;
const attachmentsUrl = (messageId: string) =>
  `${SESSION_BASE}/api/v1/messages/${messageId}/attachments`;

function makeFile(name: string, content = "contenido") {
  return new File([content], name, { type: "text/plain" });
}

const clientAgentMe = meFixture({
  capabilities: [{ capability: "ticket.reply", scope: "tenant" }],
});
const supportAgentMe = meFixture({
  capabilities: [
    { capability: "ticket.reply", scope: "global" },
    { capability: "note.internal.write", scope: "global" },
  ],
});
const clientViewerMe = meFixture({
  capabilities: [{ capability: "ticket.read", scope: "tenant" }],
});

describe("TicketReplyForm", () => {
  it("sin ticket.reply ni note.internal.write no renderiza nada", async () => {
    renderWithSession(
      <>
        <StatusProbe />
        <TicketReplyForm
          ticketId={TICKET_ID}
          resourceTenantId="22222222-2222-2222-2222-222222222222"
        />
      </>,
      { me: clientViewerMe },
    );

    // Espera a que la sesión resuelva de verdad (docstring de `renderWithSession`) antes de confirmar
    // que sigue vacío — sin esto, "sin nada en el DOM" no distingue "sin capacidad" de "aún cargando".
    await screen.findByText("status:authenticated");
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("una capacidad de ámbito tenant no aplica a un recurso de OTRO tenant (resourceTenantId)", async () => {
    renderWithSession(
      <>
        <StatusProbe />
        <TicketReplyForm
          ticketId={TICKET_ID}
          resourceTenantId="99999999-9999-9999-9999-999999999999"
        />
      </>,
      { me: clientAgentMe },
    );

    await screen.findByText("status:authenticated");
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("con solo ticket.reply: publica un mensaje público, sin selector de visibilidad", async () => {
    let posted: unknown;
    server.use(
      http.post(MESSAGES, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(
          messageFixture({ id: "new-msg", body: "Ya está resuelto", visibility: "public" }),
          { status: 201 },
        );
      }),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    const textarea = await screen.findByLabelText(/responder/i);
    expect(screen.queryByLabelText(/visibilidad/i)).not.toBeInTheDocument();

    await userEvent.type(textarea, "Ya está resuelto");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() =>
      expect(posted).toStrictEqual({ body: "Ya está resuelto", visibility: "public" }),
    );
  });

  it("con note.internal.write: puede elegir nota interna y se envía como internal", async () => {
    let posted: unknown;
    server.use(
      http.post(MESSAGES, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(
          messageFixture({ id: "new-msg", body: "Nota para el equipo", visibility: "internal" }),
          { status: 201 },
        );
      }),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: supportAgentMe },
    );

    await userEvent.type(await screen.findByLabelText(/responder/i), "Nota para el equipo");
    expect(screen.getByText("Visibilidad")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Público" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Nota interna" })).toBeInTheDocument();
    expect(screen.getByLabelText(/visibilidad/i)).toHaveAttribute("aria-label", "Visibilidad");
    await userEvent.selectOptions(screen.getByLabelText(/visibilidad/i), "internal");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() =>
      expect(posted).toStrictEqual({ body: "Nota para el equipo", visibility: "internal" }),
    );
  });

  it("el formulario tiene la región accesible con su etiqueta real", async () => {
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    await screen.findByLabelText(/responder/i);
    expect(screen.getByRole("form", { name: "Publicar mensaje" })).toBeInTheDocument();
  });

  it("no envía un mensaje vacío (validación de cliente)", async () => {
    let called = false;
    server.use(
      http.post(MESSAGES, () => {
        called = true;
        return HttpResponse.json(messageFixture(), { status: 201 });
      }),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    await userEvent.click(await screen.findByRole("button", { name: /enviar/i }));

    expect(await screen.findByText(/no puede estar vacío/i)).toBeInTheDocument();
    expect(called).toBe(false);
  });

  it("limpia el campo tras publicar con éxito", async () => {
    server.use(http.post(MESSAGES, () => HttpResponse.json(messageFixture(), { status: 201 })));
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    const textarea = await screen.findByLabelText(/responder/i);
    await userEvent.type(textarea, "Gracias por avisar");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() => expect(textarea).toHaveValue(""));
  });

  it("un error del servidor se muestra y no limpia el campo", async () => {
    // Título deliberadamente DISTINTO del genérico de cliente ("No se pudo publicar el mensaje.") —
    // si `toProblem` tomara el camino de fallback por error (en vez de usar el `title` real del
    // servidor, que sí tiene la forma `problem+json`), este test lo notaría por texto diferente.
    server.use(
      http.post(MESSAGES, () =>
        HttpResponse.json(
          { type: "about:blank", title: "Límite de mensajes alcanzado para este ticket.", status: 500 },
          { status: 500 },
        ),
      ),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    const textarea = await screen.findByLabelText(/responder/i);
    await userEvent.type(textarea, "Gracias por avisar");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    expect(
      await screen.findByText("Límite de mensajes alcanzado para este ticket."),
    ).toBeInTheDocument();
    expect(textarea).toHaveValue("Gracias por avisar");
  });

  it("un fallo de red (sin envelope problem+json) cae al mensaje de error genérico", async () => {
    server.use(http.post(MESSAGES, () => HttpResponse.error()));
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    const textarea = await screen.findByLabelText(/responder/i);
    await userEvent.type(textarea, "Gracias por avisar");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    // Sin `.title` en el error (fallo de red, no un problem+json real), `toProblem` cae al
    // `fallbackTitle` genérico en vez de reventar leyendo una propiedad que no existe.
    expect(await screen.findByText("No se pudo publicar el mensaje.")).toBeInTheDocument();
  });

  it("con un archivo: publica el mensaje y sube el adjunto al mensaje ya creado", async () => {
    // No se comprueba el nombre exacto del fichero recibido: `request.formData()` bajo MSW+jsdom no
    // preserva el filename de un `FormData` de verdad (verificado de forma aislada, es un límite del
    // entorno de test — no del código: hasta un `fetch` a pelo con `FormData` pierde el nombre igual).
    // Lo que SÍ es correcto verificar aquí es que la subida se dispara, y AL mensaje correcto; la
    // fidelidad real del multipart la cubre `tenant-user-journey.spec.ts` contra el backend real.
    let attachmentsCalled = false;
    server.use(
      http.post(MESSAGES, () =>
        HttpResponse.json(messageFixture({ id: "new-msg" }), { status: 201 }),
      ),
      http.post(attachmentsUrl("new-msg"), () => {
        attachmentsCalled = true;
        return HttpResponse.json(
          {
            id: "att-1",
            message_id: "new-msg",
            filename: "informe.pdf",
            content_type: "text/plain",
            size_bytes: 9,
          },
          { status: 201 },
        );
      }),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    await userEvent.type(await screen.findByLabelText(/responder/i), "Aquí está el informe");
    await userEvent.upload(screen.getByLabelText(/adjuntar/i), makeFile("informe.pdf"));
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() => expect(attachmentsCalled).toBe(true));
  });

  it("si el mensaje creado no trae id, el adjunto se sube con messageId vacío (sin crashear)", async () => {
    let uploadedToEmptyId = false;
    server.use(
      http.post(MESSAGES, () => {
        const noId = messageFixture();
        delete (noId as { id?: string }).id;
        return HttpResponse.json(noId, { status: 201 });
      }),
      http.post(attachmentsUrl(""), () => {
        uploadedToEmptyId = true;
        return HttpResponse.json(messageFixture(), { status: 201 });
      }),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    await userEvent.type(await screen.findByLabelText(/responder/i), "Sin id de mensaje");
    await userEvent.upload(screen.getByLabelText(/adjuntar/i), makeFile("informe.pdf"));
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() => expect(uploadedToEmptyId).toBe(true));
  });

  it("sin archivo seleccionado no sube ningún adjunto", async () => {
    let attachmentsCalled = false;
    server.use(
      http.post(MESSAGES, () =>
        HttpResponse.json(messageFixture({ id: "new-msg" }), { status: 201 }),
      ),
      http.post(attachmentsUrl("new-msg"), () => {
        attachmentsCalled = true;
        return HttpResponse.json(messageFixture(), { status: 201 });
      }),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    await userEvent.type(await screen.findByLabelText(/responder/i), "Sin adjuntos");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() => expect(screen.getByLabelText(/responder/i)).toHaveValue(""));
    expect(attachmentsCalled).toBe(false);
    expect(screen.queryByText(/el adjunto no se pudo subir/i)).not.toBeInTheDocument();
  });

  it("tras publicar con éxito, el input de fichero se resetea (no arrastra el fichero anterior)", async () => {
    let attachmentsCallCount = 0;
    server.use(
      http.post(MESSAGES, () =>
        HttpResponse.json(messageFixture({ id: "new-msg" }), { status: 201 }),
      ),
      http.post(attachmentsUrl("new-msg"), () => {
        attachmentsCallCount += 1;
        return HttpResponse.json(messageFixture(), { status: 201 });
      }),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    await userEvent.type(await screen.findByLabelText(/responder/i), "Con adjunto");
    await userEvent.upload(screen.getByLabelText(/adjuntar/i), makeFile("primero.pdf"));
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));
    await waitFor(() => expect(attachmentsCallCount).toBe(1));

    // El input de fichero (no-controlado) se remonta tras publicar (cambia su `key`) — sin esto,
    // un segundo envío SIN elegir fichero nuevo re-subiría el mismo `primero.pdf` por accidente.
    expect((screen.getByLabelText(/adjuntar/i) as HTMLInputElement).files).toHaveLength(0);

    // Segundo ciclo completo: si `setFileInputKey` no produjera un valor SIEMPRE distinto del
    // anterior (p. ej. quedara fijo en el mismo valor cada vez), este segundo remonte no ocurriría
    // y el input seguiría mostrando el fichero de este segundo adjunto tras publicar.
    await userEvent.type(await screen.findByLabelText(/responder/i), "Segundo mensaje");
    await userEvent.upload(screen.getByLabelText(/adjuntar/i), makeFile("segundo.pdf"));
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));
    await waitFor(() => expect(attachmentsCallCount).toBe(2));

    expect((screen.getByLabelText(/adjuntar/i) as HTMLInputElement).files).toHaveLength(0);
  });

  it("si el navegador reporta la selección de fichero sin FileList, no rompe (no sube nada)", async () => {
    let attachmentsCalled = false;
    server.use(
      http.post(MESSAGES, () =>
        HttpResponse.json(messageFixture({ id: "new-msg" }), { status: 201 }),
      ),
      http.post(attachmentsUrl("new-msg"), () => {
        attachmentsCalled = true;
        return HttpResponse.json(messageFixture(), { status: 201 });
      }),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    await userEvent.type(await screen.findByLabelText(/responder/i), "Sin FileList");
    const fileInput = screen.getByLabelText(/adjuntar/i);
    // Simula el caso defensivo que cubre `event.target.files?.[0] ?? null`: `files` ausente en el
    // evento (el tipo del DOM lo permite, aunque un navegador real siempre da un `FileList`).
    Object.defineProperty(fileInput, "files", { value: undefined, configurable: true });
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));

    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() => expect(screen.getByLabelText(/responder/i)).toHaveValue(""));
    expect(attachmentsCalled).toBe(false);
  });

  it("si falla la subida del adjunto, avisa pero el mensaje ya publicado no se deshace", async () => {
    server.use(
      http.post(MESSAGES, () =>
        HttpResponse.json(messageFixture({ id: "new-msg" }), { status: 201 }),
      ),
      http.post(attachmentsUrl("new-msg"), () =>
        HttpResponse.json(
          { type: "about:blank", title: "Fallo de almacenamiento", status: 502 },
          { status: 502 },
        ),
      ),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    const textarea = await screen.findByLabelText(/responder/i);
    await userEvent.type(textarea, "Con adjunto que falla");
    await userEvent.upload(screen.getByLabelText(/adjuntar/i), makeFile("roto.pdf"));
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    expect(await screen.findByText(/el adjunto no se pudo subir/i)).toBeInTheDocument();
    // El mensaje SÍ se publicó (solo el adjunto falló) — el campo se limpia igualmente.
    await waitFor(() => expect(textarea).toHaveValue(""));
  });

  it("el texto compuesto con el toolbar del editor llega intacto a la API", async () => {
    let posted: unknown;
    server.use(
      http.post(MESSAGES, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(messageFixture({ id: "new-msg" }), { status: 201 });
      }),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    const textarea = await screen.findByLabelText(/responder/i);
    await userEvent.type(textarea, "ya reviso esto");
    const toolbar = document.querySelector<HTMLElement>(".w-md-editor-toolbar");
    if (!toolbar) throw new Error("toolbar no encontrado");
    await userEvent.click(within(toolbar).getByRole("button", { name: /negrita/i }));
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() => expect(posted).toMatchObject({ visibility: "public" }));
    expect((posted as { body: string }).body).toContain("**");
  });

  it("marcado adversario tecleado en el editor queda como texto inerte, nunca se ejecuta", async () => {
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    const textarea = await screen.findByLabelText(/responder/i);
    await userEvent.type(textarea, "texto <script>window.__pwned = true;</script> normal");

    expect(textarea).toHaveValue("texto <script>window.__pwned = true;</script> normal");
    expect(document.querySelector("script")).not.toBeInTheDocument();
  });
});
