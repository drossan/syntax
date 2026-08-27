"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { useTenants } from "@/features/tenant/use-tenants";
import { problemToUi, type Problem } from "@/lib/api/problem";

import { tenantCreateSchema, toTenantCreateBody, type TenantCreateValues } from "./admin-schemas";
import { TenantSettingsToggles } from "./tenant-settings-toggles";
import { useCreateTenant } from "./use-admin";

function toProblem(error: unknown, fallbackTitle: string): Problem {
  if (error && typeof error === "object" && "title" in error) return error as Problem;
  return { type: "about:blank", title: fallbackTitle, status: 0 };
}

/**
 * Administración de tenants (clientes): listado + alta (`slug`, `name`). Solo `tenant.manage` (Soporte).
 * El contrato v0.1.0 no expone borrado/edición de tenant → CRUD = list + create (ver session log 17).
 */
export function TenantsAdmin() {
  const t = useTranslations("adminTenants");
  const tenants = useTenants(true);
  const createTenant = useCreateTenant();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<TenantCreateValues>({
    resolver: zodResolver(tenantCreateSchema),
    defaultValues: { slug: "", name: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await createTenant.mutateAsync(toTenantCreateBody(values));
      reset();
    } catch (error) {
      const ui = problemToUi(toProblem(error, t("error")), (k) => t(k));
      setFormError(ui.toast.title);
      for (const [field, message] of Object.entries(ui.fieldErrors)) {
        if (field === "slug" || field === "name") setError(field, { message });
      }
    }
  });

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>

      <form onSubmit={onSubmit} noValidate className="flex flex-wrap items-end gap-3">
        {formError ? (
          <p role="alert" className="w-full text-sm text-destructive">
            {formError}
          </p>
        ) : null}
        <label className="flex flex-col gap-1 text-sm">
          {t("slug")}
          <input
            aria-invalid={errors.slug ? true : undefined}
            className="rounded-md border px-2 py-1"
            {...register("slug")}
          />
          {errors.slug ? <span className="text-destructive">{errors.slug.message}</span> : null}
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("name")}
          <input
            aria-invalid={errors.name ? true : undefined}
            className="rounded-md border px-2 py-1"
            {...register("name")}
          />
          {errors.name ? <span className="text-destructive">{errors.name.message}</span> : null}
        </label>
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-md border px-3 py-1.5 text-sm"
        >
          {t("create")}
        </button>
      </form>

      {tenants.isLoading ? (
        <p role="status" aria-busy="true" className="text-muted-foreground">
          {t("loading")}
        </p>
      ) : tenants.isError ? (
        <div role="alert" className="flex items-center gap-3">
          <p className="text-destructive">{t("error")}</p>
          <button
            type="button"
            onClick={() => tenants.refetch()}
            className="rounded-md border px-3 py-1.5 text-sm"
          >
            {t("retry")}
          </button>
        </div>
      ) : (tenants.data?.length ?? 0) === 0 ? (
        <p role="status" className="text-muted-foreground">
          {t("empty")}
        </p>
      ) : (
        <ul className="flex flex-col gap-1 text-sm">
          {tenants.data?.map((tenant) => (
            <li key={tenant.id} className="flex flex-col gap-2 rounded-md border p-2">
              <div className="flex gap-3">
                <span className="font-medium">{tenant.name}</span>
                <span className="text-muted-foreground">{tenant.slug}</span>
              </div>
              {tenant.id ? <TenantSettingsToggles tenantId={tenant.id} /> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
