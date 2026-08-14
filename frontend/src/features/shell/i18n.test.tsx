import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useTranslations } from "next-intl";
import { describe, expect, it } from "vitest";

import enMessages from "../../../messages/en.json";
import esMessages from "../../../messages/es.json";

import { LocaleProvider, useLocaleSwitcher } from "./locale-provider";

/** Recorre las claves hoja de un objeto de mensajes → set de paths "a.b.c". */
function leafKeys(obj: unknown, prefix = ""): string[] {
  if (obj === null || typeof obj !== "object") return [prefix];
  return Object.entries(obj as Record<string, unknown>).flatMap(([key, value]) =>
    leafKeys(value, prefix ? `${prefix}.${key}` : key),
  );
}

describe("i18n completeness", () => {
  it("ES e EN tienen exactamente el mismo conjunto de claves (EN estructura completa)", () => {
    const es = leafKeys(esMessages).sort();
    const en = leafKeys(enMessages).sort();
    expect(en).toEqual(es);
  });
});

function LocaleProbe() {
  const t = useTranslations("app");
  const { setLocale } = useLocaleSwitcher();
  return (
    <div>
      <p>{t("tagline")}</p>
      <button type="button" onClick={() => setLocale("en")}>
        to-en
      </button>
    </div>
  );
}

describe("cambio de idioma", () => {
  it("al cambiar a inglés los textos visibles cambian (no hay texto hardcodeado)", async () => {
    render(
      <LocaleProvider initialLocale="es">
        <LocaleProbe />
      </LocaleProvider>,
    );

    expect(screen.getByText("Helpdesk con IA generativa")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "to-en" }));
    expect(screen.getByText("AI-powered helpdesk")).toBeInTheDocument();
    expect(screen.queryByText("Helpdesk con IA generativa")).not.toBeInTheDocument();
  });
});
