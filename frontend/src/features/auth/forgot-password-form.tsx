"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createApiClient } from "@/lib/api/client";

const forgotSchema = z.object({ email: z.string().email("Email no válido") });
type ForgotValues = z.infer<typeof forgotSchema>;

/**
 * Formulario de "olvidé mi contraseña". Tras enviar muestra SIEMPRE un mensaje neutro que no revela
 * si el email está registrado (privacidad) — el resultado de la API se ignora a propósito.
 */
export function ForgotPasswordForm({ baseUrl }: { baseUrl?: string }) {
  const [client] = useState(() => createApiClient({}, baseUrl));
  const [submitted, setSubmitted] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotValues>({
    resolver: zodResolver(forgotSchema),
    defaultValues: { email: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    await client
      .POST("/auth/password/forgot", { body: { email: values.email } })
      .catch(() => undefined);
    setSubmitted(true);
  });

  if (submitted) {
    return (
      <p role="status">
        Si el email está registrado, te hemos enviado instrucciones para restablecer la contraseña.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label htmlFor="forgot-email">Email</label>
        <input
          id="forgot-email"
          type="email"
          autoComplete="email"
          aria-invalid={errors.email ? true : undefined}
          {...register("email")}
        />
        {errors.email ? <p className="text-sm text-destructive">{errors.email.message}</p> : null}
      </div>
      <button
        type="submit"
        disabled={isSubmitting}
        aria-busy={isSubmitting}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-xs hover:opacity-90"
      >
        Enviar instrucciones
      </button>
    </form>
  );
}
