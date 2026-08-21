"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { problemToUi } from "@/lib/api/problem";

import { useAuth, type TenantSelectionChallenge } from "./auth-context";
import { TenantSelectionCards } from "./tenant-selection-cards";

const loginSchema = z.object({
  email: z.string().email("Email no válido"),
  password: z.string().min(1, "La contraseña es obligatoria"),
});

type LoginValues = z.infer<typeof loginSchema>;

/**
 * Formulario de login (RHF + Zod). En éxito lleva a la bandeja (`/`); ante error de credenciales
 * pinta el envelope `problem+json` (`problemToUi`) como alerta accesible + errores de campo.
 */
export function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const [tenantSelection, setTenantSelection] = useState<TenantSelectionChallenge | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    const { error, tenantSelection: selection } = await login(values.email, values.password);
    if (error) {
      const ui = problemToUi(error);
      setFormError(ui.toast.title);
      for (const [field, message] of Object.entries(ui.fieldErrors)) {
        if (field === "email" || field === "password") {
          setError(field, { message });
        }
      }
      return;
    }
    if (selection) {
      setTenantSelection(selection);
      return;
    }
    router.push("/");
  });

  if (tenantSelection) {
    return (
      <TenantSelectionCards
        identityToken={tenantSelection.identityToken}
        tenants={tenantSelection.tenants}
        onSuccess={() => router.push("/")}
        onCancel={() => {
          setTenantSelection(null);
          reset();
        }}
      />
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {formError ? (
        <p role="alert" className="text-sm text-destructive">
          {formError}
        </p>
      ) : null}

      <div className="flex flex-col gap-1">
        <label htmlFor="login-email">Email</label>
        <input
          id="login-email"
          type="email"
          autoComplete="email"
          aria-invalid={errors.email ? true : undefined}
          {...register("email")}
        />
        {errors.email ? <p className="text-sm text-destructive">{errors.email.message}</p> : null}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="login-password">Contraseña</label>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          aria-invalid={errors.password ? true : undefined}
          {...register("password")}
        />
        {errors.password ? (
          <p className="text-sm text-destructive">{errors.password.message}</p>
        ) : null}
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        aria-busy={isSubmitting}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-xs hover:opacity-90"
      >
        Iniciar sesión
      </button>
    </form>
  );
}
