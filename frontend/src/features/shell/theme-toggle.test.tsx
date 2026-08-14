import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { LocaleProvider } from "@/features/shell/locale-provider";
import { ThemeProvider } from "@/features/shell/theme-provider";
import { ThemeToggle } from "@/features/shell/theme-toggle";

function renderToggle() {
  return render(
    <ThemeProvider>
      <LocaleProvider>
        <ThemeToggle />
      </LocaleProvider>
    </ThemeProvider>,
  );
}

afterEach(() => {
  document.documentElement.classList.remove("dark");
  window.localStorage.clear();
});

/**
 * Escenario Gherkin: «cambio de tema» (claro→oscuro, persiste la preferencia).
 * Task frontend-helpdesk-core-06.
 */
describe("ThemeToggle", () => {
  it("activa el modo oscuro y persiste la preferencia", async () => {
    renderToggle();
    const button = screen.getByRole("button", { name: /cambiar tema/i });

    await userEvent.click(button);

    expect(document.documentElement).toHaveClass("dark");
    expect(window.localStorage.getItem("syntax-theme")).toBe("dark");
    expect(button).toHaveAttribute("aria-pressed", "true");
  });

  it("vuelve al modo claro al alternar de nuevo", async () => {
    renderToggle();
    const button = screen.getByRole("button", { name: /cambiar tema/i });

    await userEvent.click(button);
    await userEvent.click(button);

    expect(document.documentElement).not.toHaveClass("dark");
    expect(window.localStorage.getItem("syntax-theme")).toBe("light");
  });
});
