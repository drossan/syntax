"use client";

import { NextIntlClientProvider } from "next-intl";
import { createContext, useContext, useState, type ReactNode } from "react";

import enMessages from "../../../messages/en.json";
import esMessages from "../../../messages/es.json";

/** Locales soportados (ES completo, EN progresivo). */
export type Locale = "es" | "en";

const MESSAGES = { es: esMessages, en: enMessages };

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

/**
 * Provee i18n (next-intl) con locale **conmutable** en cliente. El routing por locale y la
 * persistencia se completan en la task 20; aquí basta el cambio en memoria.
 */
export function LocaleProvider({
  children,
  initialLocale = "es",
}: {
  children: ReactNode;
  initialLocale?: Locale;
}) {
  const [locale, setLocale] = useState<Locale>(initialLocale);

  return (
    <LocaleContext.Provider value={{ locale, setLocale }}>
      {/* `timeZone` explícito evita el fallback dependiente del entorno de next-intl (cross-cutting §2).
          El tz por-usuario (y `now` para tiempos relativos) llega en las tasks 12/20. */}
      <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]} timeZone="Europe/Madrid">
        {children}
      </NextIntlClientProvider>
    </LocaleContext.Provider>
  );
}

/** Accede al locale actual y su setter. Lanza fuera de `<LocaleProvider>`. */
export function useLocaleSwitcher(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocaleSwitcher debe usarse dentro de <LocaleProvider>");
  return ctx;
}
