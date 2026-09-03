"use client";

import { Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";

import { useTheme } from "./theme-provider";

/** Botón que alterna claro/oscuro. */
export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const t = useTranslations("header");

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={t("toggleTheme")}
      aria-pressed={theme === "dark"}
      className="rounded-md border px-2 py-1 text-sm"
    >
      {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}
