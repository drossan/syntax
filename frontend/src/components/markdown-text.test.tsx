import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarkdownText } from "./markdown-text";

describe("MarkdownText", () => {
  it("negrita se renderiza como <strong>", () => {
    render(<MarkdownText>{"esto es **importante**"}</MarkdownText>);
    const strong = screen.getByText("importante");
    expect(strong.tagName).toBe("STRONG");
  });

  it("un párrafo se renderiza como <p>", () => {
    render(<MarkdownText>{"texto simple de un párrafo"}</MarkdownText>);
    expect(screen.getByText("texto simple de un párrafo").tagName).toBe("P");
  });

  it("cursiva se renderiza como <em>", () => {
    render(<MarkdownText>{"esto es *sutil*"}</MarkdownText>);
    expect(screen.getByText("sutil").tagName).toBe("EM");
  });

  it("un salto de línea explícito se renderiza como <br>", () => {
    render(<MarkdownText>{"línea uno  \nlínea dos"}</MarkdownText>);
    expect(document.querySelector("br")).toBeInTheDocument();
  });

  it("tachado se renderiza como <del>", () => {
    render(<MarkdownText>{"~~obsoleto~~"}</MarkdownText>);
    expect(screen.getByText("obsoleto").tagName).toBe("DEL");
  });

  it("una lista ordenada se renderiza como <ol>", () => {
    render(<MarkdownText>{"1. primero\n2. segundo"}</MarkdownText>);
    const list = screen.getByRole("list");
    expect(list.tagName).toBe("OL");
    expect(screen.getByText("primero")).toBeInTheDocument();
    expect(screen.getByText("segundo")).toBeInTheDocument();
  });

  it("una lista no ordenada se renderiza como <ul>", () => {
    render(<MarkdownText>{"- uno\n- dos"}</MarkdownText>);
    const list = screen.getByRole("list");
    expect(list.tagName).toBe("UL");
  });

  it("una tabla (GFM) se renderiza con su estructura completa (thead/tbody/tr/th) y bordes", () => {
    render(<MarkdownText>{"| a | b |\n| - | - |\n| 1 | 2 |"}</MarkdownText>);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(document.querySelector("thead")).toBeInTheDocument();
    expect(document.querySelector("tbody")).toBeInTheDocument();
    expect(document.querySelectorAll("tr").length).toBeGreaterThanOrEqual(2);
    const th = screen.getByRole("columnheader", { name: "a" });
    expect(th.tagName).toBe("TH");
    expect(th.className).toContain("border");
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it.each([1, 2, 3, 4, 5, 6])(
    "un encabezado h%i se renderiza con peso visual moderado, no tamaño de portada",
    (level) => {
      const hashes = "#".repeat(level);
      render(<MarkdownText>{`${hashes} Título nivel ${level}`}</MarkdownText>);
      const heading = screen.getByRole("heading", { level });
      expect(heading.tagName).toBe(`H${level}`);
      expect(heading.className).toContain("text-base");
      expect(heading.className).not.toMatch(/text-(2xl|3xl|4xl)/);
    },
  );

  it("código inline se renderiza como <code>", () => {
    render(<MarkdownText>{"usa `POST /images`"}</MarkdownText>);
    expect(screen.getByText("POST /images").tagName).toBe("CODE");
  });

  it("un bloque de código se renderiza como <pre><code>", () => {
    render(<MarkdownText>{"```\nconst x = 1;\n```"}</MarkdownText>);
    const code = screen.getByText("const x = 1;");
    expect(code.tagName).toBe("CODE");
    expect(code.parentElement?.tagName).toBe("PRE");
  });

  it("una cita se renderiza como <blockquote>", () => {
    render(<MarkdownText>{"> una cita"}</MarkdownText>);
    expect(screen.getByText("una cita").closest("blockquote")).toBeInTheDocument();
  });

  it("un separador horizontal se renderiza como <hr>", () => {
    render(<MarkdownText>{"antes\n\n---\n\ndespués"}</MarkdownText>);
    expect(document.querySelector("hr")).toBeInTheDocument();
  });

  it("una URL suelta (autolink GFM) se renderiza como enlace", () => {
    render(<MarkdownText>{"visita https://example.com para más info"}</MarkdownText>);
    const link = screen.getByRole("link", { name: /example\.com/ });
    expect(link).toHaveAttribute("href", "https://example.com");
  });

  it("una casilla de tarea GFM se desenvuelve a texto plano, sin checkbox interactivo", () => {
    render(<MarkdownText>{"- [ ] paso pendiente"}</MarkdownText>);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText(/paso pendiente/)).toBeInTheDocument();
  });

  it("una imagen se renderiza con referrerPolicy, loading y alt preservado", () => {
    render(<MarkdownText>{"![captura de pantalla](https://example.com/x.png)"}</MarkdownText>);
    const img = screen.getByRole("img", { name: "captura de pantalla" });
    expect(img).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveAttribute("src", "https://example.com/x.png");
  });

  it("un enlace se abre en pestaña nueva sin arriesgar la sesión (target=_blank rel=noopener noreferrer)", () => {
    render(<MarkdownText>{"[ver más](https://example.com/docs)"}</MarkdownText>);
    const link = screen.getByRole("link", { name: "ver más" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("un enlace con protocolo javascript: queda neutralizado", () => {
    render(<MarkdownText>{"[haz clic](javascript:alert(1))"}</MarkdownText>);
    const link = screen.getByText("haz clic");
    expect(link.tagName).toBe("A");
    expect(link.getAttribute("href")).not.toMatch(/^javascript:/i);
  });

  it("una imagen con protocolo javascript: queda neutralizada", () => {
    render(<MarkdownText>{"![x](javascript:alert(1))"}</MarkdownText>);
    const img = document.querySelector("img");
    expect(img).not.toBeNull();
    expect(img?.getAttribute("src") ?? "").not.toMatch(/^javascript:/i);
  });

  it("marcado tipo script se muestra como texto inerte, nunca se ejecuta ni se inyecta como HTML", () => {
    render(<MarkdownText>{"texto <script>window.__pwned = true;</script> normal"}</MarkdownText>);
    expect(document.querySelector("script")).not.toBeInTheDocument();
    expect(screen.getByText(/script/)).toBeInTheDocument();
  });

  it("Markdown truncado a mitad de sintaxis no rompe el render", () => {
    expect(() =>
      render(<MarkdownText>{"esto es **negrita a medio cortar sin cerrar"}</MarkdownText>),
    ).not.toThrow();
    expect(screen.getByText(/negrita a medio cortar/)).toBeInTheDocument();
  });

  it("una tabla cortada a mitad de fila no rompe el render", () => {
    expect(() =>
      render(<MarkdownText>{"| a | b |\n| - | - |\n| 1 | "}</MarkdownText>),
    ).not.toThrow();
  });

  it("children vacío no rompe el render", () => {
    const { container } = render(<MarkdownText>{""}</MarkdownText>);
    expect(container).toBeInTheDocument();
  });

  it("children solo con espacios no rompe el render", () => {
    const { container } = render(<MarkdownText>{"   "}</MarkdownText>);
    expect(container).toBeInTheDocument();
  });

  it("el formato real de generate.py (negrita + lista + sección Fuentes) se renderiza formateado", () => {
    const draft =
      "Puedes **publicar el sitio** desde el panel:\n\n" +
      "1. Abre el listado\n" +
      "2. Pulsa publicar\n\n" +
      "Fuentes:\n" +
      "- [UC-API-034] Publicar y despublicar un site (intro)\n" +
      "- [UC-API-035] Qué cambios obligan a re-publicar un site (intro)";
    render(<MarkdownText>{draft}</MarkdownText>);

    expect(screen.getByText("publicar el sitio").tagName).toBe("STRONG");
    expect(screen.getAllByRole("list").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/UC-API-034/)).toBeInTheDocument();
  });
});
