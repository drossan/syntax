"use client";

import type { ReactNode } from "react";

import { OfflineBanner } from "@/features/cross-cutting/offline-banner";

import { AppHeader } from "./app-header";
import { AppNav } from "./app-nav";

/**
 * Armazón de la app autenticada: cabecera + navegación lateral (colapsa a columna en móvil) +
 * slot de contenido. Las páginas de feature del grupo `(app)` se montan en `children`.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-col">
      <OfflineBanner />
      <AppHeader />
      <div className="flex flex-1 flex-col md:flex-row">
        <aside className="border-b md:w-56 md:border-b-0 md:border-r">
          <AppNav />
        </aside>
        <main className="flex-1 p-4">{children}</main>
      </div>
    </div>
  );
}
