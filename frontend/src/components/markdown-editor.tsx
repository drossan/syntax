"use client";

import "@uiw/react-md-editor/markdown-editor.css";

import {
  bold,
  codeBlock,
  image,
  italic,
  link,
  orderedListCommand,
  quote,
  strikethrough,
  table,
  unorderedListCommand,
  type ICommand,
} from "@uiw/react-md-editor/commands";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { useMemo } from "react";

import { MarkdownText } from "@/components/markdown-text";
import { useTheme } from "@/features/shell/theme-provider";

const MDEditor = dynamic(() => import("@uiw/react-md-editor"), {
  ssr: false,
  loading: () => (
    <div role="status" className="rounded-md border px-2 py-1 text-sm text-muted-foreground">
      …
    </div>
  ),
});

/** Etiqueta (`aria-label` + `title`) de un comando — sustituye la del paquete, que viene en inglés. */
function withLabel(command: ICommand, label: string): ICommand {
  return { ...command, buttonProps: { ...command.buttonProps, "aria-label": label, title: label } };
}

/**
 * Editor de texto Markdown con toolbar (ADR-0021). Sustituye un `<textarea>` plano en las superficies
 * donde se compone/edita el texto que luego renderiza `MarkdownText` (respuesta a un ticket, alta de
 * ticket, edición de un draft de IA) — el valor que produce ES el mismo string de Markdown, sin
 * conversión.
 *
 * **Preview obligatoriamente sobreescrita con `MarkdownText`** (no el motor de preview por defecto de
 * `@uiw/react-md-editor`, que no sanea HTML embebido por defecto) — mismo allow-list ya auditado
 * (ADR-0020), y garantiza que la vista previa ES exactamente lo que se renderizará al publicar.
 *
 * **Toolbar cerrado explícitamente** (`commands`/`extraCommands`, no `commandsFilter` sobre la lista
 * por defecto): negrita, cursiva, tachado, listas, enlace, imagen, código, cita, tabla. Sin
 * `checkedListCommand` (casillas de lista-de-tareas — `MarkdownText` las desenvuelve a texto plano,
 * ADR-0020) y sin el comando nativo de alternar modo de vista (`extraCommands: []` — el modo de
 * preview queda fijo en `live`, consistente en las 3 superficies que usan este componente).
 *
 * @param value Texto Markdown actual.
 * @param onChange Nuevo valor tras cada cambio.
 */
export function MarkdownEditor({
  value,
  onChange,
  id,
  "aria-label": ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  id?: string;
  "aria-label"?: string;
}) {
  const t = useTranslations("markdownEditor");
  const { theme } = useTheme();

  const commands = useMemo<ICommand[]>(
    () => [
      withLabel(bold, t("bold")),
      withLabel(italic, t("italic")),
      withLabel(strikethrough, t("strikethrough")),
      withLabel(unorderedListCommand, t("unorderedList")),
      withLabel(orderedListCommand, t("orderedList")),
      withLabel(link, t("link")),
      withLabel(image, t("image")),
      withLabel(codeBlock, t("code")),
      withLabel(quote, t("quote")),
      withLabel(table, t("table")),
    ],
    [t],
  );

  return (
    <div data-color-mode={theme}>
      <MDEditor
        value={value}
        onChange={(next) => onChange(next ?? "")}
        preview="live"
        commands={commands}
        extraCommands={[]}
        textareaProps={{ id, "aria-label": ariaLabel }}
        components={{
          preview: (source) => <MarkdownText>{source}</MarkdownText>,
        }}
      />
    </div>
  );
}
