"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ConfirmDialog } from "@/features/tickets/confirm-dialog";
import { problemToUi, type Problem } from "@/lib/api/problem";

import { toUserInviteBody, userInviteSchema, type UserInviteValues } from "./admin-schemas";
import { useInviteUser, useRoles, useUpdateUser, useUsers } from "./use-admin";

function toProblem(error: unknown, fallbackTitle: string): Problem {
  if (error && typeof error === "object" && "title" in error) return error as Problem;
  return { type: "about:blank", title: fallbackTitle, status: 0 };
}

/**
 * Administración de usuarios del tenant: listado (server-scoped por sujeto — un `client_admin` solo ve su
 * tenant), **invitación** con rol semilla, y **deshabilitar** (soft-delete = status `disabled`) con
 * confirmación. La petición nunca lleva parámetro de tenant (aislamiento server-side).
 */
export function UsersAdmin() {
  const t = useTranslations("adminUsers");
  const users = useUsers();
  const roles = useRoles();
  const invite = useInviteUser();
  const updateUser = useUpdateUser();
  const [formError, setFormError] = useState<string | null>(null);
  const [disabling, setDisabling] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<UserInviteValues>({
    resolver: zodResolver(userInviteSchema),
    defaultValues: { email: "", roleId: "" },
  });

  const onInvite = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await invite.mutateAsync(toUserInviteBody(values));
      reset();
    } catch (error) {
      const ui = problemToUi(toProblem(error, t("error")), (k) => t(k));
      setFormError(ui.toast.title);
      if (ui.fieldErrors.email) setError("email", { message: ui.fieldErrors.email });
    }
  });

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>

      <form onSubmit={onInvite} noValidate className="flex flex-wrap items-end gap-3">
        {formError ? (
          <p role="alert" className="w-full text-sm text-destructive">
            {formError}
          </p>
        ) : null}
        <label className="flex flex-col gap-1 text-sm">
          {t("email")}
          <input
            type="email"
            aria-invalid={errors.email ? true : undefined}
            className="rounded-md border px-2 py-1"
            {...register("email")}
          />
          {errors.email ? <span className="text-destructive">{errors.email.message}</span> : null}
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("role")}
          <select aria-label={t("role")} className="rounded-md border px-2 py-1" {...register("roleId")}>
            <option value="">{t("chooseRole")}</option>
            {(roles.data ?? []).map((role) => (
              <option key={role.id} value={role.id}>
                {role.name}
              </option>
            ))}
          </select>
          {errors.roleId ? <span className="text-destructive">{errors.roleId.message}</span> : null}
        </label>
        <button type="submit" disabled={isSubmitting} className="rounded-md border px-3 py-1.5 text-sm">
          {t("invite")}
        </button>
      </form>

      {users.isLoading ? (
        <p role="status" aria-busy="true" className="text-muted-foreground">
          {t("loading")}
        </p>
      ) : users.isError ? (
        <div role="alert" className="flex items-center gap-3">
          <p className="text-destructive">{t("error")}</p>
          <button type="button" onClick={() => users.refetch()} className="rounded-md border px-3 py-1.5 text-sm">
            {t("retry")}
          </button>
        </div>
      ) : (users.data?.length ?? 0) === 0 ? (
        <p role="status" className="text-muted-foreground">
          {t("empty")}
        </p>
      ) : (
        <table aria-label={t("title")} className="w-full text-sm">
          <thead>
            <tr className="border-b text-left">
              <th scope="col" className="px-2 py-1">{t("email")}</th>
              <th scope="col" className="px-2 py-1">{t("status")}</th>
              <th scope="col" className="px-2 py-1">{t("actions")}</th>
            </tr>
          </thead>
          <tbody>
            {users.data?.map((user) => (
              <tr key={user.id} className="border-b">
                <td className="px-2 py-1">{user.email}</td>
                <td className="px-2 py-1">{user.status ? t(`statuses.${user.status}`) : "—"}</td>
                <td className="px-2 py-1">
                  {user.status !== "disabled" && user.id ? (
                    <button
                      type="button"
                      onClick={() => setDisabling(user.id ?? null)}
                      className="rounded-md border px-2 py-1"
                    >
                      {t("disable")}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {disabling ? (
        <ConfirmDialog
          title={t("disableTitle")}
          description={t("disableBody")}
          onConfirm={() => {
            updateUser.mutate({ id: disabling, status: "disabled" });
            setDisabling(null);
          }}
          onCancel={() => setDisabling(null)}
        />
      ) : null}
    </section>
  );
}
