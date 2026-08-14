"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";

import { useOnlineStatus } from "./use-online-status";

/**
 * Aviso global de **sin conexión**. Muestra una alerta accesible mientras no hay red y, al **recuperar**
 * la conexión, invalida las queries para **reintentar las lecturas** (cross-cutting §; T7). Cuando hay
 * conexión no renderiza nada.
 */
export function OfflineBanner() {
  const t = useTranslations("offline");
  const online = useOnlineStatus();
  const queryClient = useQueryClient();
  const wasOffline = useRef(false);

  useEffect(() => {
    if (!online) {
      wasOffline.current = true;
    } else if (wasOffline.current) {
      wasOffline.current = false;
      void queryClient.invalidateQueries();
    }
  }, [online, queryClient]);

  if (online) return null;

  return (
    <div role="alert" className="bg-destructive px-4 py-1 text-center text-sm text-destructive-foreground">
      {t("message")}
    </div>
  );
}
