"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

/** Tema de la interfaz. */
export type Theme = "light" | "dark";

const STORAGE_KEY = "syntax-theme";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

/**
 * Provee el tema y lo aplica a `<html>` (clase `dark` de Tailwind v4), **persistiendo** la preferencia
 * en `localStorage`. Al montar respeta lo guardado o la preferencia del sistema.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    const initial: Theme =
      stored === "light" || stored === "dark"
        ? stored
        : window.matchMedia?.("(prefers-color-scheme: dark)")?.matches
          ? "dark"
          : "light";
    // Sincroniza desde storage/sistema tras el montaje. SSR-safe: el server renderiza 'light' y el
    // cliente ajusta al hidratar (el script anti-flash se añade en la task 20).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(initial);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const toggleTheme = () => setTheme((current) => (current === "dark" ? "light" : "dark"));

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

/** Accede al tema y sus acciones. Lanza fuera de `<ThemeProvider>`. */
export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme debe usarse dentro de <ThemeProvider>");
  return ctx;
}
