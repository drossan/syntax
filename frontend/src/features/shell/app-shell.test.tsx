import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/features/shell/locale-provider";

vi.mock("./app-header", () => ({ AppHeader: () => <div>Header</div> }));
vi.mock("./app-nav", () => ({ AppNav: () => <div>Nav</div> }));
vi.mock("@/features/cross-cutting/offline-banner", () => ({ OfflineBanner: () => null }));

import { AppShell } from "./app-shell";

function renderShell() {
  return render(
    <LocaleProvider>
      <AppShell>
        <p>Contenido</p>
      </AppShell>
    </LocaleProvider>,
  );
}

describe("AppShell", () => {
  it("en móvil, la navegación empieza colapsada y un botón la despliega", async () => {
    renderShell();

    const nav = screen.getByText("Nav").closest("aside")!;
    expect(nav.className).toContain("hidden");

    const toggle = screen.getByRole("button", { name: /abrir navegación/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(toggle);

    expect(nav.className).not.toContain("hidden");
    expect(screen.getByRole("button", { name: /cerrar navegación/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});
