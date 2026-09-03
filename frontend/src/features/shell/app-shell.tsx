"use client";

import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { OfflineBanner } from "@/features/cross-cutting/offline-banner";

import { AppHeader } from "./app-header";
import { AppNav } from "./app-nav";

/**
 * Armazón de la app autenticada: cabecera + navegación lateral + slot de contenido. En móvil la
 * navegación arranca colapsada (era una lista de 7 enlaces por delante del contenido) y un botón la
 * despliega; en desktop (`md:`) siempre visible.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const t = useTranslations("nav");
  const [navOpen, setNavOpen] = useState(false);

  return (
    <div className="flex min-h-full flex-col">
      <OfflineBanner />
      <AppHeader />
      <div className="flex flex-1 flex-col md:flex-row">
        <button
          type="button"
          onClick={() => setNavOpen((current) => !current)}
          aria-expanded={navOpen}
          aria-controls="app-nav"
          className="border-b px-4 py-2 text-left text-sm font-medium md:hidden"
        >
          {navOpen ? t("closeMenu") : t("openMenu")}
        </button>
        <aside
          id="app-nav"
          className={`border-b md:block md:w-56 md:border-b-0 md:border-r ${navOpen ? "block" : "hidden"}`}
        >
          <AppNav />
        </aside>
        <main className="flex-1 p-4">{children}</main>
      </div>
    </div>
  );
}
