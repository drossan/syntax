"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import type { components } from "@/types/api";

import { addRole } from "./role-ops";
import { useUpdateUser } from "./use-admin";

type User = components["schemas"]["User"];
type Role = components["schemas"]["Role"];

/**
 * Asigna un **rol semilla** a un usuario: muestra sus roles actuales y un selector para añadir uno más
 * (`PATCH /admin/users/{id}` con el conjunto de roles resultante, sin duplicar). Acotado por `role.manage`
 * (el guard de la página) y por tenant (server-side).
 *
 * @param user Usuario a modificar.
 * @param seedRoles Catálogo de roles semilla asignables.
 */
export function RoleAssignment({ user, seedRoles }: { user: User; seedRoles: Role[] }) {
  const t = useTranslations("adminRoles");
  const updateUser = useUpdateUser();
  const [selected, setSelected] = useState("");

  const current = user.roles ?? [];

  function assign() {
    if (selected === "" || !user.id) return;
    updateUser.mutate({ id: user.id, roles: addRole(current, selected) });
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="font-medium">{user.email}</span>
      <span className="text-muted-foreground">{current.join(", ") || t("noRoles")}</span>
      <select
        aria-label={t("assignRoleTo", { email: user.email ?? "" })}
        value={selected}
        onChange={(event) => setSelected(event.target.value)}
        className="rounded-md border px-2 py-1"
      >
        <option value="">{t("chooseRole")}</option>
        {seedRoles.map((role) => (
          <option key={role.id} value={role.id}>
            {role.name}
          </option>
        ))}
      </select>
      <button type="button" onClick={assign} className="rounded-md border px-3 py-1.5">
        {t("assign")}
      </button>
    </div>
  );
}
