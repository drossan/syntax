"use client";

import { useFormatter, useTranslations } from "next-intl";
import Link from "next/link";

import { useKbDocument, useKbRelated } from "./use-kb";

/**
 * Vista de un documento de la KB (`GET /kb/documents/{uc_id}`): metadata (dominio/package/estado/fecha),
 * enlace a la fuente, y **relacionados** por dominio (heurística; el contrato no expone un grafo). Un
 * documento inaccesible (404) muestra no-encontrado. El título es texto inerte.
 *
 * @param ucId Clave del documento a mostrar.
 */
export function KbDocument({ ucId }: { ucId: string }) {
  const t = useTranslations("kb");
  const format = useFormatter();
  const doc = useKbDocument(ucId);
  const related = useKbRelated(doc.data?.domain, ucId);

  if (doc.isError) {
    return (
      <p role="status" className="p-4 text-muted-foreground">
        {t("notFound")}
      </p>
    );
  }

  if (doc.isLoading || !doc.data) {
    return (
      <p role="status" aria-busy="true" className="p-4 text-muted-foreground">
        {t("loading")}
      </p>
    );
  }

  const document = doc.data;

  return (
    <article className="flex flex-col gap-4">
      <header className="flex flex-col gap-2 border-b pb-4">
        <h1 className="text-xl font-semibold tracking-tight">{document.title}</h1>
        <dl className="flex flex-wrap gap-4 text-sm text-muted-foreground">
          <span>{document.domain}</span>
          <span>{document.package}</span>
          <span>{document.estado ? t(`estados.${document.estado}`) : null}</span>
          {document.updated ? (
            <time dateTime={document.updated}>
              {format.dateTime(new Date(document.updated), { dateStyle: "medium" })}
            </time>
          ) : null}
        </dl>
        {document.source_url ? (
          <a href={document.source_url} className="text-sm text-primary underline">
            {t("openSource")}
          </a>
        ) : null}
      </header>

      {(related.data?.length ?? 0) > 0 ? (
        <nav aria-label={t("related")} className="flex flex-col gap-1">
          <h2 className="text-sm font-medium">{t("related")}</h2>
          <ul className="flex flex-col gap-1 text-sm">
            {related.data?.map((doc) => (
              <li key={doc.uc_id}>
                <Link href={`/kb/${doc.uc_id}`} className="text-primary underline">
                  {doc.title}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
    </article>
  );
}
