import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

import { TenantSettingsToggles } from "./tenant-settings-toggles";

const TENANT_ID = "tenant-1";
const SETTINGS = `${SESSION_BASE}/api/v1/admin/settings`;
const me = meFixture({ capabilities: [{ capability: "tenant.settings.manage", scope: "global" }] });

describe("TenantSettingsToggles", () => {
  it("pinta el valor actual de auto_approve y ai_auto_draft", async () => {
    server.use(
      http.get(SETTINGS, () => HttpResponse.json({ auto_approve: true, ai_auto_draft: false })),
    );

    renderWithSession(<TenantSettingsToggles tenantId={TENANT_ID} />, { me });

    const autoApprove = await screen.findByRole("checkbox", { name: /auto-aprobar/i });
    const aiAutoDraft = screen.getByRole("checkbox", { name: /auto-generar draft/i });
    expect(autoApprove).toBeChecked();
    expect(aiAutoDraft).not.toBeChecked();
  });

  it("al marcar ai_auto_draft, envía AMBOS campos (PATCH reemplaza el objeto completo)", async () => {
    let sent: { auto_approve: boolean; ai_auto_draft: boolean } | undefined;
    server.use(
      http.get(SETTINGS, () => HttpResponse.json({ auto_approve: true, ai_auto_draft: false })),
      http.patch(SETTINGS, async ({ request }) => {
        sent = (await request.json()) as { auto_approve: boolean; ai_auto_draft: boolean };
        return HttpResponse.json(sent);
      }),
    );

    renderWithSession(<TenantSettingsToggles tenantId={TENANT_ID} />, { me });
    const aiAutoDraft = await screen.findByRole("checkbox", { name: /auto-generar draft/i });
    await userEvent.click(aiAutoDraft);

    await waitFor(() => expect(sent).toStrictEqual({ auto_approve: true, ai_auto_draft: true }));
  });

  it("un fallo al guardar muestra el error sin perder el valor mostrado", async () => {
    server.use(
      http.get(SETTINGS, () => HttpResponse.json({ auto_approve: false, ai_auto_draft: true })),
      http.patch(SETTINGS, () =>
        HttpResponse.json(
          { type: "about:blank", title: "fallo simulado", status: 500 },
          { status: 500 },
        ),
      ),
    );

    renderWithSession(<TenantSettingsToggles tenantId={TENANT_ID} />, { me });
    const autoApprove = await screen.findByRole("checkbox", { name: /auto-aprobar/i });
    await userEvent.click(autoApprove);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
