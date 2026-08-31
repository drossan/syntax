"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import { Can } from "@/features/rbac/can";

/** Entradas de navegación con la capacidad que las habilita (rbac.md). */
const NAV_ITEMS = [
  { key: "inbox", href: "/", capability: "ticket.read" },
  { key: "approvals", href: "/approvals", capability: "approval.decide" },
  { key: "kb", href: "/kb", capability: "kb.read" },
  { key: "dashboard", href: "/dashboard", capability: "analytics.read" },
  { key: "tenants", href: "/admin/tenants", capability: "tenant.manage" },
  { key: "users", href: "/admin/users", capability: "user.manage" },
  { key: "roles", href: "/admin/roles", capability: "role.manage" },
] as const;

/** Navegación principal: solo muestra las entradas que la sesión puede usar (`<Can>`). */
export function AppNav() {
  const t = useTranslations("nav");

  return (
    <nav aria-label="Navegación principal" className="flex flex-col gap-1 p-2">
      {NAV_ITEMS.map((item) => (
        <Can key={item.key} capability={item.capability}>
          <Link href={item.href} className="rounded-md px-3 py-2 text-sm hover:bg-accent">
            {t(item.key)}
          </Link>
        </Can>
      ))}
    </nav>
  );
}
