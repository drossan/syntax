"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createApiClient } from "@/lib/api/client";
import { problemToUi } from "@/lib/api/problem";

const setPasswordSchema = z
  .object({
    password: z.string().min(8, "Usa al menos 8 caracteres"),
    confirm: z.string(),
  })
  .refine((values) => values.password === values.confirm, {
    path: ["confirm"],
    message: "Las contraseñas no coinciden",
  });

type SetPasswordValues = z.infer<typeof setPasswordSchema>;

/** Modo del formulario: reset de contraseña o aceptación de invitación (mismo endpoint + token). */
export type SetPasswordMode = "reset" | "invite";

/**
 * Formulario para fijar una contraseña con un token de un solo uso (`POST /auth/password/reset`).
 * Sirve para reset y para aceptar invitación (`mode`). Token inválido/caducado → error claro con
 * enlace para re-solicitar. Fuerza mínima validada por Zod (≥ 8, coherente con el contrato).
 */
export function SetPasswordForm({
  token,
  baseUrl,
  mode = "reset",
}: {
  token: string;
  baseUrl?: string;
  mode?: SetPasswordMode;
}) {
  const [client] = useState(() => createApiClient({}, baseUrl));
  const [done, setDone] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SetPasswordValues>({
    resolver: zodResolver(setPasswordSchema),
    defaultValues: { password: "", confirm: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    const { error } = await client.POST("/auth/password/reset", {
      body: { token, new_password: values.password },
    });
    if (error) {
      setFormError(problemToUi(error).toast.title);
      return;
    }
    setDone(true);
  });

  if (done) {
    return (
      <div role="status" className="flex flex-col gap-3">
        <p>
          {mode === "invite"
            ? "Tu cuenta ya está activa. Inicia sesión para empezar."
            : "Contraseña actualizada. Ya puedes iniciar sesión."}
        </p>
        <Link href="/login" className="text-primary underline underline-offset-4">
          Iniciar sesión
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {formError ? (
        <div role="alert" className="flex flex-col gap-2 text-sm text-destructive">
          <p>{formError}</p>
          <Link href="/password/forgot" className="text-primary underline underline-offset-4">
            Solicitar un nuevo enlace
          </Link>
        </div>
      ) : null}

      <div className="flex flex-col gap-1">
        <label htmlFor="new-password">Nueva contraseña</label>
        <input
          id="new-password"
          type="password"
          autoComplete="new-password"
          aria-invalid={errors.password ? true : undefined}
          {...register("password")}
        />
        {errors.password ? (
          <p className="text-sm text-destructive">{errors.password.message}</p>
        ) : null}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="confirm-password">Repite la contraseña</label>
        <input
          id="confirm-password"
          type="password"
          autoComplete="new-password"
          aria-invalid={errors.confirm ? true : undefined}
          {...register("confirm")}
        />
        {errors.confirm ? (
          <p className="text-sm text-destructive">{errors.confirm.message}</p>
        ) : null}
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        aria-busy={isSubmitting}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-xs hover:opacity-90"
      >
        {mode === "invite" ? "Activar cuenta" : "Guardar contraseña"}
      </button>
    </form>
  );
}
