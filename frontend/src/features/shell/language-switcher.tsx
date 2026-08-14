"use client";

import { useTranslations } from "next-intl";

import { useLocaleSwitcher, type Locale } from "./locale-provider";

/** Selector de idioma (ES/EN) cableado a `LocaleProvider`. */
export function LanguageSwitcher() {
  const { locale, setLocale } = useLocaleSwitcher();
  const t = useTranslations("header");

  return (
    <select
      aria-label={t("language")}
      value={locale}
      onChange={(event) => setLocale(event.target.value as Locale)}
      className="rounded-md border px-2 py-1 text-sm"
    >
      <option value="es">ES</option>
      <option value="en">EN</option>
    </select>
  );
}
