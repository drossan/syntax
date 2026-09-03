import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { LocaleProvider, type Locale } from "@/features/shell/locale-provider";
import { ThemeProvider, useTheme } from "@/features/shell/theme-provider";

import { MarkdownEditor } from "./markdown-editor";

/** Envoltorio mínimo (tema + i18n) para testear el editor de forma aislada, sin el stack de sesión. */
function renderEditor(
  props: Partial<React.ComponentProps<typeof MarkdownEditor>> = {},
  options?: { locale?: Locale },
) {
  function Controlled() {
    const [value, setValue] = useState(props.value ?? "");
    return (
      <MarkdownEditor
        value={value}
        onChange={(next) => {
          setValue(next);
          props.onChange?.(next);
        }}
        id={props.id}
        aria-label={props["aria-label"]}
      />
    );
  }

  return render(
    <ThemeProvider>
      <LocaleProvider initialLocale={options?.locale ?? "es"}>
        <Controlled />
      </LocaleProvider>
    </ThemeProvider>,
  );
}

/** El toolbar del paquete es un `<ul>` sin `role="toolbar"` — se localiza por su clase, tras esperar a
 * que el editor real (cargado vía `next/dynamic`) sustituya el estado de carga. */
async function findToolbar(): Promise<HTMLElement> {
  await screen.findByRole("button", { name: /negrita|bold/i });
  const toolbar = document.querySelector<HTMLElement>(".w-md-editor-toolbar");
  if (!toolbar) throw new Error("toolbar no encontrado");
  return toolbar;
}

/** El panel de preview (`.w-md-editor-preview`) usa `MarkdownText` (override); el panel de EDICIÓN
 * (`preview="live"` muestra ambos a la vez) tiene su propio resaltado de sintaxis que también puede
 * contener el mismo texto — acotar a `.w-md-editor-preview` evita falsos positivos de "múltiples
 * coincidencias" entre los dos paneles. */
async function findPreview(): Promise<HTMLElement> {
  await screen.findByRole("button", { name: /negrita|bold/i });
  const preview = document.querySelector<HTMLElement>(".w-md-editor-preview");
  if (!preview) throw new Error("preview no encontrado");
  return preview;
}

describe("MarkdownEditor", () => {
  it("muestra un estado de carga antes de que el editor se hidrate", () => {
    renderEditor();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("monta el editor real tras hidratarse, con el toolbar completo", async () => {
    renderEditor();
    const toolbar = await findToolbar();
    const buttons = within(toolbar).getAllByRole("button");
    const labels = buttons.map((b) => b.getAttribute("aria-label"));

    for (const expected of [
      "Negrita",
      "Cursiva",
      "Tachado",
      "Lista sin ordenar",
      "Lista ordenada",
      "Enlace",
      "Imagen",
      "Bloque de código",
      "Cita",
      "Tabla",
    ]) {
      expect(labels).toContain(expected);
    }
  });

  it("no incluye el comando de casilla de lista-de-tareas ni el botón nativo de modo de vista", async () => {
    renderEditor();
    const toolbar = await findToolbar();
    const buttons = within(toolbar).getAllByRole("button");
    const labels = buttons.map((b) => (b.getAttribute("aria-label") ?? "").toLowerCase());

    expect(labels.some((l) => l.includes("checked") || l.includes("task"))).toBe(false);
    expect(labels.some((l) => l.includes("edit code") || l.includes("live code"))).toBe(false);
    expect(buttons).toHaveLength(10);
  });

  it("la vista previa renderiza el Markdown formateado, con el mismo MarkdownText", async () => {
    renderEditor({ value: "esto es **importante**" });
    const preview = await findPreview();
    expect(within(preview).getByText("importante").tagName).toBe("STRONG");
  });

  it("la vista previa muestra el marcado adversario como texto inerte", async () => {
    renderEditor({ value: "texto <script>window.__pwned = true;</script> normal" });
    const preview = await findPreview();
    expect(within(preview).getByText(/normal/)).toBeInTheDocument();
    expect(document.querySelector("script")).not.toBeInTheDocument();
  });

  it("una casilla de lista-de-tareas tecleada a mano se desenvuelve a texto plano, sin checkbox", async () => {
    renderEditor({ value: "- [ ] paso pendiente" });
    const preview = await findPreview();
    expect(within(preview).getByText(/paso pendiente/)).toBeInTheDocument();
    expect(document.querySelector('input[type="checkbox"]')).not.toBeInTheDocument();
  });

  it("usar el comando de negrita del toolbar inserta la sintaxis y actualiza el valor", async () => {
    renderEditor();
    const toolbar = await findToolbar();
    const boldButton = within(toolbar).getByRole("button", { name: "Negrita" });

    await userEvent.click(boldButton);

    const textarea = document.querySelector("textarea");
    expect(textarea).not.toBeNull();
    expect(textarea?.value).toContain("**");
  });

  it("borrar todo el contenido notifica un string vacío, nunca undefined", async () => {
    let lastValue: string | undefined;
    renderEditor({
      value: "algo de texto",
      onChange: (next) => {
        lastValue = next;
      },
    });
    const textarea = await screen.findByRole("textbox");

    await userEvent.clear(textarea);

    expect(lastValue).toBe("");
    expect((textarea as HTMLTextAreaElement).value).toBe("");
  });

  it("el data-color-mode del editor sigue el tema activo", async () => {
    const { container } = renderEditor();
    await findToolbar();
    expect(container.querySelector('[data-color-mode="light"]')).toBeInTheDocument();
  });

  it("cambiar el tema mientras el editor está montado actualiza data-color-mode sin recargar", async () => {
    function ThemeToggle() {
      const { toggleTheme } = useTheme();
      return (
        <button type="button" onClick={toggleTheme}>
          cambiar tema
        </button>
      );
    }
    const { container } = render(
      <ThemeProvider>
        <LocaleProvider>
          <ThemeToggle />
          <MarkdownEditor value="" onChange={() => {}} />
        </LocaleProvider>
      </ThemeProvider>,
    );
    await findToolbar();
    expect(container.querySelector('[data-color-mode="light"]')).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /cambiar tema/i }));

    expect(container.querySelector('[data-color-mode="dark"]')).toBeInTheDocument();
    // El editor sigue montado con el mismo texto, no se remonta desde cero.
    expect(document.querySelector("textarea")).not.toBeNull();
  });

  it("las etiquetas del toolbar cambian con el idioma de la sesión", async () => {
    renderEditor({}, { locale: "en" });
    const toolbar = await findToolbar();
    expect(within(toolbar).getByRole("button", { name: "Bold" })).toBeInTheDocument();
  });

  it("pasa el id y el aria-label al textarea subyacente, para la accesibilidad del label existente", async () => {
    renderEditor({ id: "ticket-reply-body", "aria-label": "Cuerpo de la respuesta" });
    await findToolbar();
    const textarea = document.querySelector("textarea#ticket-reply-body");
    expect(textarea).not.toBeNull();
    expect(textarea?.getAttribute("aria-label")).toBe("Cuerpo de la respuesta");
  });

  it("pegar una imagen en el editor no la embebe como data URI (ADR-0021)", async () => {
    renderEditor();
    const textarea = await screen.findByRole("textbox");

    const file = new File(["contenido-binario"], "captura.png", { type: "image/png" });
    const clipboardData = {
      files: [file],
      items: [{ kind: "file", type: "image/png", getAsFile: () => file }],
      getData: () => "",
      types: ["Files"],
    };
    const pasteEvent = new Event("paste", { bubbles: true, cancelable: true });
    Object.defineProperty(pasteEvent, "clipboardData", { value: clipboardData });
    textarea.dispatchEvent(pasteEvent);

    expect((textarea as HTMLTextAreaElement).value).not.toContain("data:image");
    expect((textarea as HTMLTextAreaElement).value).not.toMatch(/base64/);
  });
});
