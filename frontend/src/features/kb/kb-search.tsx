"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";

import type { components } from "@/types/api";

import type { KbSearchInput } from "./kb-query";
import { useKbSearch } from "./use-kb";

type KBDomain = components["schemas"]["KBDomain"];
type KBEstado = components["schemas"]["KBEstado"];

/** Dominios de la KB (contrato `KBDomain`). */
const DOMAINS: KBDomain[] = [
  "analytics-logs-and-activity",
  "authoring-and-editor",
  "content-modeling-and-schemas",
  "data-collection-and-store",
  "data-packs-and-distributors",
  "forms-and-submissions",
  "i18n-and-translations",
  "identity-and-permissions",
  "integrations-crm-and-feeds",
  "media-and-dam",
  "navigation-and-menus",
  "platform-and-devex",
  "render-infra-and-config",
  "rendering-and-publishing",
  "search-ai-and-llms",
  "seo-sitemaps-and-edge",
  "sites-domains-instances",
];

const ESTADOS: KBEstado[] = ["draft", "active"];

/**
 * Buscador semántico de la KB: término + filtros (dominio/estado), resultados con título/dominio/estado/
 * snippet, y estados loading / error+reintento / empty (reformular) / sin-buscar. El texto de los
 * snippets se renderiza como texto inerte (anti-XSS).
 */
export function KbSearch() {
  const t = useTranslations("kb");
  const [q, setQ] = useState("");
  const [domain, setDomain] = useState<KBDomain | "">("");
  const [estado, setEstado] = useState<KBEstado | "">("");
  const [submitted, setSubmitted] = useState<KbSearchInput | null>(null);

  const { data, isFetching, isError, refetch } = useKbSearch(submitted);

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (q.trim().length === 0) return;
    setSubmitted({
      q: q.trim(),
      ...(domain ? { domain } : {}),
      ...(estado ? { estado } : {}),
    });
  }

  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>

      <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-3">
        <input
          type="search"
          aria-label={t("searchLabel")}
          placeholder={t("searchPlaceholder")}
          value={q}
          onChange={(event) => setQ(event.target.value)}
          className="min-w-64 flex-1 rounded-md border px-2 py-1"
        />
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted-foreground">{t("domain")}</span>
          <select
            aria-label={t("domain")}
            value={domain}
            onChange={(event) => setDomain(event.target.value as KBDomain | "")}
            className="rounded-md border px-2 py-1"
          >
            <option value="">{t("all")}</option>
            {DOMAINS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted-foreground">{t("estado")}</span>
          <select
            aria-label={t("estado")}
            value={estado}
            onChange={(event) => setEstado(event.target.value as KBEstado | "")}
            className="rounded-md border px-2 py-1"
          >
            <option value="">{t("all")}</option>
            {ESTADOS.map((value) => (
              <option key={value} value={value}>
                {t(`estados.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="rounded-md border px-3 py-1.5 text-sm">
          {t("search")}
        </button>
      </form>

      {isError ? (
        <div role="alert" className="flex flex-col items-start gap-2">
          <p className="text-destructive">{t("error")}</p>
          <button type="button" onClick={() => refetch()} className="rounded-md border px-3 py-1.5 text-sm">
            {t("retry")}
          </button>
        </div>
      ) : submitted === null ? (
        <p className="text-muted-foreground">{t("prompt")}</p>
      ) : isFetching && !data ? (
        <p role="status" aria-busy="true" className="text-muted-foreground">
          {t("loading")}
        </p>
      ) : (data?.items.length ?? 0) === 0 ? (
        <p role="status" className="rounded-md border border-dashed p-8 text-muted-foreground">
          {t("empty")}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {data?.items.map((hit) => (
            <li key={hit.uc_id} className="flex flex-col gap-1 rounded-md border p-3">
              <Link href={`/kb/${hit.uc_id}`} className="font-medium text-primary underline">
                {hit.title}
              </Link>
              <div className="flex gap-2 text-xs text-muted-foreground">
                <span>{hit.domain}</span>
                <span>·</span>
                <span>{hit.estado ? t(`estados.${hit.estado}`) : null}</span>
              </div>
              <p className="text-sm text-muted-foreground">{hit.snippet}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
