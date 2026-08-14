import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useTranslations } from "next-intl";
import { describe, expect, it } from "vitest";

import { LanguageSwitcher } from "@/features/shell/language-switcher";
import { LocaleProvider } from "@/features/shell/locale-provider";

function InboxLabel() {
  const t = useTranslations("nav");
  return <span>{t("inbox")}</span>;
}

/**
 * Escenario Gherkin: «cambio de idioma» (ES→EN, los textos cambian).
 * Task frontend-helpdesk-core-06.
 */
describe("LanguageSwitcher", () => {
  it("cambia los textos de la interfaz de español a inglés", async () => {
    render(
      <LocaleProvider>
        <InboxLabel />
        <LanguageSwitcher />
      </LocaleProvider>,
    );

    expect(screen.getByText("Bandeja")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByRole("combobox", { name: /idioma/i }), "en");

    expect(await screen.findByText("Inbox")).toBeInTheDocument();
    expect(screen.queryByText("Bandeja")).not.toBeInTheDocument();
  });
});
