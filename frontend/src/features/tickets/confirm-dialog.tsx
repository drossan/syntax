"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

/**
 * Diálogo de confirmación accesible (`role="alertdialog"`, `aria-modal`) para acciones destructivas.
 * Enfoca el botón de cancelar al abrir (opción segura) y cierra con Escape. Confirmar/cancelar delegan
 * en el llamante; no muta nada por sí mismo. `children` permite insertar contenido adicional (p.ej. un
 * formulario de nota obligatoria) entre la descripción y los botones, sin perder el foco/overlay/Escape
 * reales que un `role="alertdialog"` anuncia — no los reimplementes en el llamante.
 *
 * @param title Título del diálogo.
 * @param description Texto explicativo de la consecuencia.
 * @param children Contenido adicional opcional (formulario, aviso) antes de los botones.
 * @param confirmLabel Etiqueta del botón de confirmar (default: `ticketActions.confirm`).
 * @param cancelLabel Etiqueta del botón de cancelar (default: `ticketActions.cancel`).
 * @param confirmDisabled Deshabilita el botón de confirmar (p.ej. mientras la mutación está en vuelo).
 * @param onConfirm Callback al confirmar.
 * @param onCancel Callback al cancelar (también en Escape).
 */
export function ConfirmDialog({
  title,
  description,
  children,
  confirmLabel,
  cancelLabel,
  confirmDisabled,
  onConfirm,
  onCancel,
}: {
  title: string;
  description: string;
  children?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmDisabled?: boolean;
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
        {children}
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
            disabled={confirmDisabled}
            className="rounded-md border bg-destructive px-3 py-1.5 text-sm text-destructive-foreground disabled:opacity-50"
          >
            {confirmLabel ?? t("confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
