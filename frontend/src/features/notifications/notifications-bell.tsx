"use client";

import { Bell } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { unreadCount } from "./notifications";
import { useNotifications, useMarkRead } from "./use-notifications";

/**
 * Campana de notificaciones in-app: badge con el conteo de no leídas, lista desplegable con el tipo y la
 * fecha de cada notificación, y acción de marcar leída. Se sondea por polling (`useNotifications`). El
 * contenido es texto inerte (los tipos se localizan).
 *
 * @param pollMs Intervalo de sondeo (default del hook).
 */
export function NotificationsBell({ pollMs }: { pollMs?: number }) {
  const t = useTranslations("notifications");
  const format = useFormatter();
  const { data } = useNotifications(pollMs);
  const markRead = useMarkRead();
  const [open, setOpen] = useState(false);

  const items = data ?? [];
  const unread = unreadCount(items);

  return (
    <div className="relative">
      <button
        type="button"
        aria-label={t("bell", { count: unread })}
        onClick={() => setOpen((value) => !value)}
        className="rounded-md border px-2 py-1 text-sm"
      >
        <Bell className="inline size-4" aria-hidden="true" />
        {unread > 0 ? (
          <span className="ml-1 rounded-full bg-primary px-1 text-xs text-primary-foreground">
            {unread}
          </span>
        ) : null}
      </button>

      {open ? (
        items.length === 0 ? (
          <p role="status" className="absolute right-0 mt-1 w-64 rounded-md border bg-background p-3 text-sm text-muted-foreground">
            {t("empty")}
          </p>
        ) : (
          <ul
            aria-label={t("list")}
            className="absolute right-0 mt-1 flex w-72 flex-col gap-1 rounded-md border bg-background p-2 text-sm shadow-lg"
          >
            {items.map((notification) => (
              <li key={notification.id} className="flex items-center justify-between gap-2 rounded-md p-1">
                <span className="flex flex-col">
                  <span className={notification.read_at ? "text-muted-foreground" : "font-medium"}>
                    {t(`types.${notification.type}`)}
                  </span>
                  {notification.created_at ? (
                    <time dateTime={notification.created_at} className="text-xs text-muted-foreground">
                      {format.dateTime(new Date(notification.created_at), { dateStyle: "medium", timeStyle: "short" })}
                    </time>
                  ) : null}
                </span>
                {!notification.read_at && notification.id ? (
                  <button
                    type="button"
                    onClick={() => markRead.mutate(notification.id ?? "")}
                    className="rounded-md border px-2 py-0.5 text-xs"
                  >
                    {t("markRead")}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}
