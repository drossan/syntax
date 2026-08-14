"use client";

import { useTranslations } from "next-intl";

import { slaLevel } from "./sla";

/** Clases por nivel de SLA (indicador visual). */
const LEVEL_CLASS: Record<"normal" | "imminent" | "overdue", string> = {
  normal: "text-muted-foreground",
  imminent: "font-medium text-amber-600 dark:text-amber-400",
  overdue: "font-semibold text-destructive",
};

/**
 * Indicador visual del SLA de un ticket. Deriva el nivel de `sla_due` (`slaLevel`) y lo pinta
 * localizado. Sin SLA → guion neutro. `now` lo provee el contenedor (una sola lectura de reloj por
 * render de la bandeja) para mantener el componente puro y determinista en tests.
 *
 * @param slaDue Fecha límite del SLA del ticket (ISO) o `null`.
 * @param now Instante de referencia en ms (epoch).
 */
export function SlaBadge({ slaDue, now }: { slaDue: string | null | undefined; now: number }) {
  const t = useTranslations("tickets.sla");
  const level = slaLevel(slaDue, now);

  if (level === "none") {
    return <span className="text-muted-foreground">{t("none")}</span>;
  }
  return (
    <span className={LEVEL_CLASS[level]} data-sla={level}>
      {t(level)}
    </span>
  );
}
