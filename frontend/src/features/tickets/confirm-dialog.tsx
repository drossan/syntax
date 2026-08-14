"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";

/**
 * Diálogo de confirmación accesible (`role="alertdialog"`, `aria-modal`) para acciones destructivas.
 * Enfoca el botón de cancelar al abrir (opción segura) y cierra con Escape. Confirmar/cancelar delegan
 * en el llamante; no muta nada por sí mismo.
 *
 * @param title Título del diálogo.
 * @param description Texto explicativo de la consecuencia.
 * @param confirmLabel Etiqueta del botón de confirmar (default: `ticketActions.confirm`).
 * @param cancelLabel Etiqueta del botón de cancelar (default: `ticketActions.cancel`).
 * @param onConfirm Callback al confirmar.
 * @param onCancel Callback al cancelar (también en Escape).
 */
export function ConfirmDialog({
  title,
  description,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
}: {
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const t = useTranslations("ticketActions");
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-description"
        onKeyDown={(event) => {
          if (event.key === "Escape") onCancel();
        }}
        className="flex max-w-sm flex-col gap-4 rounded-lg border bg-background p-6 shadow-lg"
      >
        <h2 id="confirm-title" className="text-lg font-semibold">
          {title}
        </h2>
        <p id="confirm-description" className="text-sm text-muted-foreground">
          {description}
        </p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            ref={cancelRef}
            onClick={onCancel}
            className="rounded-md border px-3 py-1.5 text-sm"
          >
            {cancelLabel ?? t("cancel")}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-md border bg-destructive px-3 py-1.5 text-sm text-destructive-foreground"
          >
            {confirmLabel ?? t("confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
