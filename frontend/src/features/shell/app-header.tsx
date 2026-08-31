"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import { useLogout } from "@/features/auth/auth-context";
import { NotificationsBell } from "@/features/notifications/notifications-bell";
import { TenantSwitcher } from "@/features/tenant/tenant-switcher";

import { LanguageSwitcher } from "./language-switcher";
import { ThemeToggle } from "./theme-toggle";

/**
 * Cabecera de la app autenticada: marca, tenant switcher (05), campana de notificaciones (20, polling),
 * selector de idioma, toggle de tema, cuenta (cambiar contraseña) y cierre de sesión.
 */
export function AppHeader() {
  const t = useTranslations("header");
  const logout = useLogout();

  return (
    <header className="flex items-center justify-between gap-4 border-b px-4 py-2">
      <span className="font-semibold tracking-tight">Syntax</span>
      <div className="flex items-center gap-3">
        <TenantSwitcher />
        <NotificationsBell />
        <LanguageSwitcher />
        <ThemeToggle />
        <Link href="/account" className="rounded-md border px-3 py-1 text-sm hover:bg-accent">
          {t("account")}
        </Link>
        <button
          type="button"
          onClick={() => void logout()}
          className="rounded-md border px-3 py-1 text-sm"
        >
          {t("logout")}
        </button>
      </div>
    </header>
  );
}
