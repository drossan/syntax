"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { MarkdownText } from "@/components/markdown-text";
import type { components } from "@/types/api";

import { isPending, noteProvided } from "./approval-status";
import { useApproveApproval, useEditApproval, useRejectApproval } from "./use-approval-decision";

type ApprovalTask = components["schemas"]["ApprovalTask"];

/**
 * Acciones de decisión sobre un draft IA: **aprobar** (publica tal cual), **editar y aprobar** (publica
 * el texto editado) y **rechazar** (nota-al-humano obligatoria + **confirm**; no publica). Idempotencia:
 * si la aprobación ya no está `pending`, informa "ya resuelta" y no ofrece acciones. Si no hay borrador
 * (run fallido), ofrece reintentar/escalar. El texto es inerte (anti-XSS).
 *
 * @param approval La `ApprovalTask` a decidir, o `undefined` si no hay borrador.
 * @param onRetry Acción opcional de reintento/escalado cuando no hay borrador.
 */
export function ApprovalDecision({
  approval,
  onRetry,
}: {
  approval?: ApprovalTask;
  onRetry?: () => void;
}) {
  const t = useTranslations("approvalDecision");
  const approve = useApproveApproval(approval?.id ?? "");
  const edit = useEditApproval(approval?.id ?? "");
  const reject = useRejectApproval(approval?.id ?? "");
  const [editing, setEditing] = useState(false);
  const [draftText, setDraftText] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState(false);

  if (!approval) {
    return (
      <div role="status" className="flex flex-col items-start gap-2">
        <p className="text-muted-foreground">{t("noDraft")}</p>
        {onRetry ? (
          <button type="button" onClick={onRetry} className="rounded-md border px-3 py-1.5 text-sm">
            {t("retry")}
          </button>
        ) : null}
      </div>
    );
  }

  if (!isPending(approval.status)) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        {t("resolved")}
      </p>
    );
  }

  function confirmReject() {
    if (!noteProvided(note)) {
      setNoteError(true);
      return;
    }
    reject.mutate({ human_note: note }, { onSuccess: () => setRejecting(false) });
  }

  return (
    <div className="flex flex-col gap-3">
      <blockquote className="border-l-2 pl-3 text-sm">
        <MarkdownText>{approval.draft_body ?? ""}</MarkdownText>
      </blockquote>

      {editing ? (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-sm">
            {t("draftLabel")}
            <textarea
              aria-label={t("draftLabel")}
              value={draftText}
              onChange={(event) => setDraftText(event.target.value)}
              rows={5}
              className="rounded-md border px-2 py-1"
            />
          </label>
          <button
            type="button"
            onClick={() => edit.mutate({ final_body: draftText })}
            className="self-start rounded-md border px-3 py-1.5 text-sm"
          >
            {t("editApprove")}
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => approve.mutate(undefined)}
            className="rounded-md border bg-primary px-3 py-1.5 text-sm text-primary-foreground"
          >
            {t("approve")}
          </button>
          <button
            type="button"
            onClick={() => {
              setDraftText(approval.draft_body ?? "");
              setEditing(true);
            }}
            className="rounded-md border px-3 py-1.5 text-sm"
          >
            {t("edit")}
          </button>
          <button
            type="button"
            onClick={() => setRejecting(true)}
            className="rounded-md border px-3 py-1.5 text-sm"
          >
            {t("reject")}
          </button>
        </div>
      )}

      {rejecting ? (
        <div
          role="alertdialog"
          aria-modal="true"
          aria-label={t("rejectTitle")}
          className="flex flex-col gap-2 rounded-md border p-3"
        >
          <label className="flex flex-col gap-1 text-sm">
            {t("noteLabel")}
            <textarea
              aria-label={t("noteLabel")}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={3}
              className="rounded-md border px-2 py-1"
            />
          </label>
          {noteError ? <p className="text-sm text-destructive">{t("noteRequired")}</p> : null}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setRejecting(false);
                setNote("");
                setNoteError(false);
              }}
              className="rounded-md border px-3 py-1.5 text-sm"
            >
              {t("cancel")}
            </button>
            <button
              type="button"
              onClick={confirmReject}
              className="rounded-md border bg-destructive px-3 py-1.5 text-sm text-destructive-foreground"
            >
              {t("confirmReject")}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
