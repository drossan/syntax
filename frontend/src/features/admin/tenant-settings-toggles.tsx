"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { useTenantSettings, useUpdateTenantSettings } from "./use-admin";

/**
 * `auto_approve`/`ai_auto_draft` de UN tenant (`GET/PATCH /admin/settings?tenant_id=`). Antes de esta
 * task, ninguna pantalla exponía estos dos ajustes — solo editables por API cruda.
 *
 * `PATCH /admin/settings` **reemplaza el objeto completo** (no hace merge parcial pese al verbo): el
 * checkbox envía SIEMPRE los dos campos juntos (el valor actual del que no cambió + el nuevo del que
 * sí), nunca solo el campo tocado — enviar uno solo resetearía el otro a su default del schema.
 *
 * @param tenantId Id del tenant cuyos ajustes se editan.
 */
export function TenantSettingsToggles({ tenantId }: { tenantId: string }) {
  const t = useTranslations("adminTenants.settings");
  const settings = useTenantSettings(tenantId);
  const update = useUpdateTenantSettings(tenantId);
  const [saveError, setSaveError] = useState(false);

  if (settings.isLoading || !settings.data) return null;

  function toggle(field: "auto_approve" | "ai_auto_draft") {
    if (!settings.data) return;
    setSaveError(false);
    update.mutate(
      { ...settings.data, [field]: !settings.data[field] },
      { onError: () => setSaveError(true) },
    );
  }

  return (
    <div className="flex flex-col gap-1 text-sm">
      {saveError ? (
        <p role="alert" className="text-destructive">
          {t("saveError")}
        </p>
      ) : null}
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={settings.data.auto_approve ?? false}
          disabled={update.isPending}
          onChange={() => toggle("auto_approve")}
        />
        {t("autoApprove")}
      </label>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={settings.data.ai_auto_draft ?? true}
          disabled={update.isPending}
          onChange={() => toggle("ai_auto_draft")}
        />
        {t("aiAutoDraft")}
      </label>
    </div>
  );
}
