import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { meFixture, notificationFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

const NOTIFS = `${SESSION_BASE}/api/v1/notifications`;

let readCalls: string[] = [];
afterEach(() => {
  readCalls = [];
});

function serveNotifications(getItems: () => ReturnType<typeof notificationFixture>[]) {
  server.use(
    http.get(NOTIFS, () => {
      const items = getItems();
      return HttpResponse.json({ items, page: 1, page_size: 20, total: items.length });
    }),
    http.patch(`${NOTIFS}/:id/read`, ({ params }) => {
      readCalls.push(params.id as string);
      return HttpResponse.json(notificationFixture({ id: params.id as string, read_at: "2026-08-13T12:00:00Z" }));
    }),
  );
}

describe("NotificationsBell", () => {
  it("las notificaciones se actualizan por polling y la campana refleja el nuevo conteo", async () => {
    let items = [notificationFixture({ id: "a", read_at: null })];
    serveNotifications(() => items);

    const { NotificationsBell } = await import("./notifications-bell");
    renderWithSession(<NotificationsBell pollMs={20} />, { me: meFixture() });

    expect(await screen.findByText("1")).toBeInTheDocument();

    // Llega una notificación nueva en el servidor; el polling la refleja.
    items = [notificationFixture({ id: "a", read_at: null }), notificationFixture({ id: "b", read_at: null })];
    expect(await screen.findByText("2")).toBeInTheDocument();
  });

  it("marcar una notificación como leída deja de contar como no leída", async () => {
    const items = [
      notificationFixture({ id: "a", read_at: null }),
      notificationFixture({ id: "b", read_at: null }),
    ];
    // Al marcar leída, el servidor la refleja como leída en el siguiente GET.
    serveNotifications(() => items);
    server.use(
      http.patch(`${NOTIFS}/:id/read`, ({ params }) => {
        readCalls.push(params.id as string);
        const target = items.find((n) => n.id === params.id);
        if (target) target.read_at = "2026-08-13T12:00:00Z";
        return HttpResponse.json(notificationFixture({ id: params.id as string, read_at: "2026-08-13T12:00:00Z" }));
      }),
    );

    const { NotificationsBell } = await import("./notifications-bell");
    renderWithSession(<NotificationsBell pollMs={2000} />, { me: meFixture() });

    await userEvent.click(await screen.findByRole("button", { name: /notificaciones/i }));
    const list = await screen.findByRole("list", { name: /notificaciones/i });
    await userEvent.click(within(list).getAllByRole("button", { name: /marcar leíd/i })[0]!);

    await waitFor(() => expect(readCalls).toContain("a"));
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });
});
