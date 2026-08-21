import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { useApprovals } from "@/features/approvals/use-approvals";
import { useAuth } from "@/features/auth/auth-context";
import { TenantSwitcher } from "@/features/tenant/tenant-switcher";
import { useTickets } from "@/features/tickets/use-tickets";
import {
  approvalPageFixture,
  approvalTaskFixture,
  meFixture,
  tenantChoiceFixture,
  ticketFixture,
  ticketPageFixture,
  tokenFixture,
} from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

function StatusProbe() {
  return <span>status:{useAuth().status}</span>;
}

function TicketsProbe() {
  const { data } = useTickets({});
  return <span>tickets:{data?.items.map((t) => t.subject).join(",") ?? "-"}</span>;
}

function ApprovalsProbe() {
  const { data } = useApprovals();
  return <span>approvals:{data?.items.map((a) => a.id).join(",") ?? "-"}</span>;
}

const ME = `${SESSION_BASE}/api/v1/auth/me`;
const SWITCH_TENANT = `${SESSION_BASE}/api/v1/auth/switch-tenant`;
const TICKETS = `${SESSION_BASE}/api/v1/tickets`;
const APPROVALS = `${SESSION_BASE}/api/v1/approvals`;

const TENANT_A = tenantChoiceFixture({ id: "t1", slug: "acme", name: "Tenant A" });
const TENANT_B = tenantChoiceFixture({ id: "t2", slug: "globex", name: "Tenant B" });

/**
 * Escenarios Gherkin (CU-FE-02): visibilidad del selector por conteo de tenants (no por capacidad),
 * switch real con éxito/error/pendiente, tenant activo marcado, y aislamiento de caché entre tenants
 * (tickets y aprobaciones). Task frontend-multi-tenant-login-04.
 */
describe("TenantSwitcher", () => {
  it("cualquier usuario con 2+ tenants ve el selector (no solo Soporte)", async () => {
    renderWithSession(<TenantSwitcher />, {
      me: meFixture({
        capabilities: [{ capability: "ticket.read", scope: "tenant" }],
        active_tenant_id: "t1",
        available_tenants: [TENANT_A, TENANT_B],
      }),
    });

    const select = await screen.findByRole("combobox", { name: "Tenant activo" });
    expect(screen.getByRole("option", { name: "Tenant A" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Tenant B" })).toBeInTheDocument();
    expect((select as HTMLSelectElement).value).toBe("t1");
  });

  it("con una sola membresía no hay selector que mostrar (aunque tenga ámbito global)", async () => {
    renderWithSession(
      <>
        <StatusProbe />
        <TenantSwitcher />
      </>,
      {
        me: meFixture({
          capabilities: [{ capability: "ticket.read", scope: "global" }],
          available_tenants: [TENANT_A],
        }),
      },
    );

    await screen.findByText("status:authenticated");
    expect(screen.queryByRole("combobox", { name: "Tenant activo" })).not.toBeInTheDocument();
  });

  it("elegir un tenant completa el switch: los datos cargados son del tenant nuevo", async () => {
    let ticketsCall = 0;
    server.use(
      http.get(TICKETS, () => {
        ticketsCall += 1;
        return HttpResponse.json(
          ticketsCall === 1
            ? ticketPageFixture([ticketFixture({ subject: "Ticket de Tenant A" })])
            : ticketPageFixture([ticketFixture({ subject: "Ticket de Tenant B" })]),
        );
      }),
      http.post(SWITCH_TENANT, () => HttpResponse.json(tokenFixture())),
    );

    renderWithSession(
      <>
        <TenantSwitcher />
        <TicketsProbe />
      </>,
      {
        me: meFixture({ active_tenant_id: "t1", available_tenants: [TENANT_A, TENANT_B] }),
      },
    );

    await screen.findByText("tickets:Ticket de Tenant A");

    server.use(
      http.get(ME, () =>
        HttpResponse.json(
          meFixture({ active_tenant_id: "t2", available_tenants: [TENANT_A, TENANT_B] }),
        ),
      ),
    );
    const select = await screen.findByRole("combobox", { name: "Tenant activo" });
    await userEvent.selectOptions(select, "t2");

    await screen.findByText("tickets:Ticket de Tenant B");
    expect((select as HTMLSelectElement).value).toBe("t2");
  });

  it("cambiar de tenant falla sin alterar la vista actual (caché no se limpia)", async () => {
    server.use(
      http.get(TICKETS, () =>
        HttpResponse.json(ticketPageFixture([ticketFixture({ subject: "Ticket de Tenant A" })])),
      ),
      http.post(SWITCH_TENANT, () =>
        HttpResponse.json(
          { type: "about:blank", title: "Cambio de tenant rechazado", status: 403 },
          { status: 403 },
        ),
      ),
    );

    renderWithSession(
      <>
        <TenantSwitcher />
        <TicketsProbe />
      </>,
      {
        me: meFixture({ active_tenant_id: "t1", available_tenants: [TENANT_A, TENANT_B] }),
      },
    );

    await screen.findByText("tickets:Ticket de Tenant A");
    const select = await screen.findByRole("combobox", { name: "Tenant activo" });

    await userEvent.selectOptions(select, "t2");

    expect(await screen.findByRole("alert")).toHaveTextContent(/cambio de tenant rechazado/i);
    expect((select as HTMLSelectElement).value).toBe("t1");
    expect(screen.getByText("tickets:Ticket de Tenant A")).toBeInTheDocument();
  });

  it("el selector se deshabilita mientras resuelve (sin elegir otro a la vez)", async () => {
    let resolveSwitch: (() => void) | undefined;
    server.use(
      http.post(SWITCH_TENANT, async () => {
        await new Promise<void>((resolve) => {
          resolveSwitch = resolve;
        });
        return HttpResponse.json(tokenFixture());
      }),
      http.get(ME, () =>
        HttpResponse.json(
          meFixture({ active_tenant_id: "t2", available_tenants: [TENANT_A, TENANT_B] }),
        ),
      ),
    );

    renderWithSession(<TenantSwitcher />, {
      me: meFixture({ active_tenant_id: "t1", available_tenants: [TENANT_A, TENANT_B] }),
    });

    const select = await screen.findByRole("combobox", { name: "Tenant activo" });
    await userEvent.selectOptions(select, "t2");

    await waitFor(() => expect(select).toBeDisabled());

    resolveSwitch?.();
    await waitFor(() => expect(select).not.toBeDisabled());
  });

  it("la cola de aprobaciones no se filtra entre tenants (respuesta tardía no pisa la vista nueva)", async () => {
    let resolveFirstApprovals: (() => void) | undefined;
    let approvalsCall = 0;
    server.use(
      http.get(APPROVALS, async () => {
        approvalsCall += 1;
        if (approvalsCall === 1) {
          await new Promise<void>((resolve) => {
            resolveFirstApprovals = resolve;
          });
          return HttpResponse.json(
            approvalPageFixture([approvalTaskFixture({ id: "tenant-a-approval" })]),
          );
        }
        return HttpResponse.json(
          approvalPageFixture([approvalTaskFixture({ id: "tenant-b-approval" })]),
        );
      }),
      http.post(SWITCH_TENANT, () => HttpResponse.json(tokenFixture())),
    );

    renderWithSession(
      <>
        <TenantSwitcher />
        <ApprovalsProbe />
      </>,
      {
        me: meFixture({
          capabilities: [{ capability: "approval.decide", scope: "global" }],
          active_tenant_id: "t1",
          available_tenants: [TENANT_A, TENANT_B],
        }),
      },
    );

    await waitFor(() => expect(approvalsCall).toBe(1));

    server.use(
      http.get(ME, () =>
        HttpResponse.json(
          meFixture({
            capabilities: [{ capability: "approval.decide", scope: "global" }],
            active_tenant_id: "t2",
            available_tenants: [TENANT_A, TENANT_B],
          }),
        ),
      ),
    );
    const select = await screen.findByRole("combobox", { name: "Tenant activo" });
    await userEvent.selectOptions(select, "t2");

    await screen.findByText("approvals:tenant-b-approval");

    resolveFirstApprovals?.();
    await waitFor(() =>
      expect(screen.getByText("approvals:tenant-b-approval")).toBeInTheDocument(),
    );
  });
});
