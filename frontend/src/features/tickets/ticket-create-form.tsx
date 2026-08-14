"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { useUnsavedGuard } from "@/features/cross-cutting/use-unsaved-guard";
import { problemToUi, type Problem } from "@/lib/api/problem";

import { ticketCreateSchema, toTicketCreateBody, type TicketCreateValues } from "./ticket-create-schema";
import { useCreateTicket } from "./use-create-ticket";

const PRIORITIES = ["low", "normal", "high", "urgent"] as const;

/** Coerción defensiva de un error de mutación (desconocido) al envelope `problem+json`. */
function toProblem(error: unknown, fallbackTitle: string): Problem {
  if (error && typeof error === "object" && "title" in error) return error as Problem;
  return { type: "about:blank", title: fallbackTitle, status: 0 };
}

/**
 * Formulario de alta de ticket (RHF + Zod). Valida en cliente (asunto requerido); en éxito navega al
 * detalle del ticket creado; ante 422 mapea el envelope a errores de campo (`problemToUi`). El dominio
 * lo clasifica el backend (no se envía).
 */
export function TicketCreateForm() {
  const t = useTranslations("ticketCreate");
  const router = useRouter();
  const createTicket = useCreateTicket();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<TicketCreateValues>({
    resolver: zodResolver(ticketCreateSchema),
    defaultValues: { subject: "", body: "", priority: "normal" },
  });

  // Guard de cambios sin guardar (nav-guard, task 22): pide confirmación al abandonar con cambios.
  useUnsavedGuard(isDirty);

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      const ticket = await createTicket.mutateAsync(toTicketCreateBody(values));
      router.push(`/tickets/${ticket.id}`);
    } catch (error) {
      const ui = problemToUi(toProblem(error, t("genericError")), (k) => t(k));
      setFormError(ui.toast.title);
      for (const [field, message] of Object.entries(ui.fieldErrors)) {
        if (field === "subject" || field === "body" || field === "priority") {
          setError(field, { message });
        }
      }
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex max-w-xl flex-col gap-4">
      <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>

      {formError ? (
        <p role="alert" className="text-sm text-destructive">
          {formError}
        </p>
      ) : null}

      <div className="flex flex-col gap-1">
        <label htmlFor="ticket-subject">{t("subject")}</label>
        <input
          id="ticket-subject"
          aria-invalid={errors.subject ? true : undefined}
          className="rounded-md border px-2 py-1"
          {...register("subject")}
        />
        {errors.subject ? (
          <p className="text-sm text-destructive">{errors.subject.message}</p>
        ) : null}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="ticket-body">{t("body")}</label>
        <textarea
          id="ticket-body"
          rows={5}
          aria-invalid={errors.body ? true : undefined}
          className="rounded-md border px-2 py-1"
          {...register("body")}
        />
        {errors.body ? <p className="text-sm text-destructive">{errors.body.message}</p> : null}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="ticket-priority">{t("priority")}</label>
        <select
          id="ticket-priority"
          className="rounded-md border px-2 py-1"
          {...register("priority")}
        >
          {PRIORITIES.map((value) => (
            <option key={value} value={value}>
              {t(`priorities.${value}`)}
            </option>
          ))}
        </select>
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        aria-busy={isSubmitting}
        className="self-start rounded-md border px-3 py-1.5"
      >
        {t("submit")}
      </button>
    </form>
  );
}
