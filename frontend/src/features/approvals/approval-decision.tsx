"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { MarkdownEditor } from "@/components/markdown-editor";
import { MarkdownText } from "@/components/markdown-text";
import { ConfirmDialog } from "@/features/tickets/confirm-dialog";
import type { components } from "@/types/api";

import { isPending, noteProvided } from "./approval-status";
import { useApproveApproval, useEditApproval, useRejectApproval } from "./use-approval-decision";

type ApprovalTask = components["schemas"]["ApprovalTask"];

/** Umbral (caracteres) a partir del cual el draft se trunca por defecto en la cola. */
const DRAFT_PREVIEW_THRESHOLD = 240;

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
  const [expanded, setExpanded] = useState(false);

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

  const hasDraft = (approval.draft_body ?? "").trim().length > 0;
  const isLong = (approval.draft_body?.length ?? 0) > DRAFT_PREVIEW_THRESHOLD;

  return (
    <div className="flex flex-col gap-3">
      {hasDraft ? (
        <>
          <blockquote
            className={`border-l-2 pl-3 text-sm ${isLong && !expanded ? "line-clamp-4" : ""}`}
          >
            <MarkdownText>{approval.draft_body ?? ""}</MarkdownText>
          </blockquote>
          {isLong ? (
            <button
              type="button"
              onClick={() => setExpanded((current) => !current)}
              className="self-start text-sm text-primary underline"
            >
              {expanded ? t("showLess") : t("showMore")}
            </button>
          ) : null}
        </>
      ) : (
        <div role="status" className="flex flex-col gap-1 rounded-md border border-dashed p-3 text-sm">
          <p className="font-medium">{t("noDraftGenerated")}</p>
          {approval.human_note ? (
            <p className="text-muted-foreground">{approval.human_note}</p>
          ) : null}
        </div>
      )}

      {editing ? (
        <div className="flex flex-col gap-2">
          <span className="text-sm">{t("draftLabel")}</span>
          <MarkdownEditor
            aria-label={t("draftLabel")}
            value={draftText}
            onChange={setDraftText}
          />
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
            disabled={approve.isPending}
            className="rounded-md border bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
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
        <ConfirmDialog
          title={t("rejectTitle")}
          description={t("rejectDescription")}
          confirmLabel={t("confirmReject")}
          cancelLabel={t("cancel")}
          confirmDisabled={reject.isPending}
          onCancel={() => {
            setRejecting(false);
            setNote("");
            setNoteError(false);
          }}
          onConfirm={confirmReject}
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
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
