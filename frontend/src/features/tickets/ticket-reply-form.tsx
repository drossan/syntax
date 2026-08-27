"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { useCan } from "@/features/rbac/use-can";
import { problemToUi, type Problem } from "@/lib/api/problem";

import {
  ticketReplySchema,
  toMessageCreateBody,
  type TicketReplyValues,
} from "./ticket-reply-schema";
import { useReplyTicket } from "./use-ticket-reply";

/** Coerción defensiva de un error de mutación (desconocido) al envelope `problem+json`. */
function toProblem(error: unknown, fallbackTitle: string): Problem {
  if (error && typeof error === "object" && "title" in error) return error as Problem;
  return { type: "about:blank", title: fallbackTitle, status: 0 };
}

/**
 * Publica un mensaje en el hilo del ticket (`POST /tickets/{id}/messages`). Sin `ticket.reply` ni
 * `note.internal.write` no renderiza nada (no hay nada que este sujeto pueda publicar). Con solo
 * `ticket.reply` el mensaje siempre es público (sin selector); con `note.internal.write` también puede
 * elegir nota interna. Limpia el campo tras publicar; un error de servidor lo conserva para reintentar.
 *
 * @param ticketId Id del ticket.
 * @param resourceTenantId Tenant del ticket (ámbito de las capacidades).
 */
export function TicketReplyForm({
  ticketId,
  resourceTenantId,
}: {
  ticketId: string;
  resourceTenantId?: string | null;
}) {
  const t = useTranslations("ticketReply");
  const canReplyPublic = useCan("ticket.reply", { resourceTenantId });
  const canWriteInternal = useCan("note.internal.write", { resourceTenantId });
  const reply = useReplyTicket(ticketId);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isSubmitting, dirtyFields },
  } = useForm<TicketReplyValues>({
    resolver: zodResolver(ticketReplySchema),
    defaultValues: { body: "", visibility: canReplyPublic ? "public" : "internal" },
  });

  // `canReplyPublic`/`canWriteInternal` fallan cerrado (`useCan`) hasta que la sesión resuelve
  // (`GET /auth/me`) — en el primer render son `false` aunque el sujeto sí tenga la capacidad, y
  // `defaultValues` de RHF se captura UNA vez al montar, no se re-evalúa solo. Sin este efecto, un
  // sujeto con solo `ticket.reply` (sin selector de visibilidad en el DOM que lo corrija) quedaría
  // publicando SIEMPRE como `internal` (reproducido: bug real, no hipotético). No toca `body` — no
  // pisa lo que el usuario ya esté escribiendo — y no pisa una elección de visibilidad ya hecha.
  useEffect(() => {
    if (!dirtyFields.visibility) {
      setValue("visibility", canReplyPublic ? "public" : "internal");
    }
  }, [canReplyPublic, dirtyFields.visibility, setValue]);

  if (!canReplyPublic && !canWriteInternal) return null;

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await reply.mutateAsync(toMessageCreateBody(values));
      reset({ body: "", visibility: values.visibility });
    } catch (error) {
      const ui = problemToUi(toProblem(error, t("genericError")), (k) => t(k));
      setFormError(ui.toast.title);
    }
  });

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label={t("region")}
      className="flex flex-col gap-2 border-t pt-4"
    >
      {formError ? (
        <p role="alert" className="text-sm text-destructive">
          {formError}
        </p>
      ) : null}

      <div className="flex flex-col gap-1">
        <label htmlFor="ticket-reply-body">{t("replyLabel")}</label>
        <textarea
          id="ticket-reply-body"
          rows={3}
          aria-invalid={errors.body ? true : undefined}
          className="rounded-md border px-2 py-1"
          {...register("body")}
        />
        {errors.body ? <p className="text-sm text-destructive">{errors.body.message}</p> : null}
      </div>

      {canWriteInternal ? (
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">{t("visibilityLabel")}</span>
          <select
            aria-label={t("visibilityLabel")}
            className="rounded-md border px-2 py-1"
            {...register("visibility")}
          >
            {canReplyPublic ? <option value="public">{t("visibilityPublic")}</option> : null}
            <option value="internal">{t("visibilityInternal")}</option>
          </select>
        </label>
      ) : null}

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
