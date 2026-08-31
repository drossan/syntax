"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { problemToUi, type Problem } from "@/lib/api/problem";

import { useChangePassword } from "./use-change-password";

const changePasswordSchema = z
  .object({
    currentPassword: z.string().min(1, "Introduce tu contraseña actual"),
    newPassword: z.string().min(8, "Usa al menos 8 caracteres"),
    confirmNewPassword: z.string(),
  })
  .refine((values) => values.newPassword === values.confirmNewPassword, {
    path: ["confirmNewPassword"],
    message: "Las contraseñas no coinciden",
  });

type ChangePasswordValues = z.infer<typeof changePasswordSchema>;

/** Coerción defensiva de un error de mutación (desconocido) al envelope `problem+json`. */
function toProblem(error: unknown, fallbackTitle: string): Problem {
  if (error && typeof error === "object" && "title" in error) return error as Problem;
  return { type: "about:blank", title: fallbackTitle, status: 0 };
}

/**
 * Cambia la contraseña del usuario ya autenticado (`POST /auth/password/change`) — endpoint que
 * existía en el contrato y el backend desde antes, sin ningún componente del front que lo llamara.
 * Un 401 (contraseña actual incorrecta) conserva el formulario para reintentar; en éxito, limpia y
 * confirma. La sesión actual sigue siendo válida tras el cambio (el backend no la revoca).
 */
export function ChangePasswordForm() {
  const t = useTranslations("account");
  const changePassword = useChangePassword();
  const [formError, setFormError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { currentPassword: "", newPassword: "", confirmNewPassword: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await changePassword.mutateAsync({
        current_password: values.currentPassword,
        new_password: values.newPassword,
      });
      reset();
      setDone(true);
    } catch (error) {
      const ui = problemToUi(toProblem(error, t("genericError")));
      setFormError(ui.toast.title);
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex max-w-sm flex-col gap-4">
      <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>

      {done ? <p role="status">{t("success")}</p> : null}
      {formError ? (
        <p role="alert" className="text-sm text-destructive">
          {formError}
        </p>
      ) : null}

      <div className="flex flex-col gap-1">
        <label htmlFor="change-password-current">{t("currentPassword")}</label>
        <input
          id="change-password-current"
          type="password"
          autoComplete="current-password"
          aria-invalid={errors.currentPassword ? true : undefined}
          {...register("currentPassword")}
        />
        {errors.currentPassword ? (
          <p className="text-sm text-destructive">{errors.currentPassword.message}</p>
        ) : null}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="change-password-new">{t("newPassword")}</label>
        <input
          id="change-password-new"
          type="password"
          autoComplete="new-password"
          aria-invalid={errors.newPassword ? true : undefined}
          {...register("newPassword")}
        />
        {errors.newPassword ? (
          <p className="text-sm text-destructive">{errors.newPassword.message}</p>
        ) : null}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="change-password-confirm">{t("confirmNewPassword")}</label>
        <input
          id="change-password-confirm"
          type="password"
          autoComplete="new-password"
          aria-invalid={errors.confirmNewPassword ? true : undefined}
          {...register("confirmNewPassword")}
        />
        {errors.confirmNewPassword ? (
          <p className="text-sm text-destructive">{errors.confirmNewPassword.message}</p>
        ) : null}
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        aria-busy={isSubmitting}
        className="self-start rounded-md border px-3 py-1.5 text-sm"
      >
        {t("submit")}
      </button>
    </form>
  );
}
