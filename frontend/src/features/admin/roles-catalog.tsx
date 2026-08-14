"use client";

import { useTranslations } from "next-intl";

import { RoleAssignment } from "./role-assignment";
import { useRoles, useUsers } from "./use-admin";

/**
 * Vista **read-only** del catálogo de roles semilla (con sus capacidades) + **asignación** de rol semilla
 * por usuario. **Sin composer** de roles custom en Fase 1 (diferido C6): se muestra un aviso de que llegará
 * con el enforcement real. Nombres de rol/capacidad son texto inerte.
 */
export function RolesCatalog() {
  const t = useTranslations("adminRoles");
  const roles = useRoles();
  const users = useUsers();
  const seedRoles = (roles.data ?? []).filter((role) => role.kind === "system");

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>

      <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
        {t("composerSoon")}
      </p>

      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-medium">{t("catalog")}</h2>
        {roles.isLoading ? (
          <p role="status" aria-busy="true" className="text-muted-foreground">
            {t("loading")}
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {(roles.data ?? []).map((role) => (
              <li key={role.id} className="rounded-md border p-3">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{role.name}</span>
                  <span className="text-xs text-muted-foreground">{role.kind}</span>
                </div>
                <ul className="mt-1 flex flex-wrap gap-1">
                  {(role.capabilities ?? []).map((capability) => (
                    <li key={capability} className="rounded bg-accent px-1.5 py-0.5 font-mono text-xs">
                      {capability}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-medium">{t("assignSection")}</h2>
        {(users.data ?? []).map((user) => (
          <RoleAssignment key={user.id} user={user} seedRoles={seedRoles} />
        ))}
      </div>
    </section>
  );
}
