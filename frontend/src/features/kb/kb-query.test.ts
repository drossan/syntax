import { describe, expect, it } from "vitest";

import {
  buildKbSearchQuery,
  kbDocumentKey,
  kbRelatedKey,
  kbSearchKey,
  relatedDocuments,
} from "./kb-query";

/** Query de búsqueda KB y derivación de relacionados. */
describe("buildKbSearchQuery", () => {
  it("incluye q y aplica defaults de paginación", () => {
    expect(buildKbSearchQuery({ q: "publicar" })).toStrictEqual({ q: "publicar", page: 1, page_size: 20 });
  });

  it("incluye solo los filtros definidos", () => {
    const query = buildKbSearchQuery({ q: "x", domain: "authoring-and-editor", estado: "active" });
    expect(query.domain).toBe("authoring-and-editor");
    expect(query.estado).toBe("active");
    expect(query).not.toHaveProperty("package");
  });

  it("clampa la página a >= 1 y trunca fraccionarias", () => {
    expect(buildKbSearchQuery({ q: "x", page: 0 }).page).toBe(1);
    expect(buildKbSearchQuery({ q: "x", page: 3 }).page).toBe(3);
    expect(buildKbSearchQuery({ q: "x", page: 2.9 }).page).toBe(2);
  });
});

describe("claves de caché KB", () => {
  it("kbSearchKey keyea por input (null sin término)", () => {
    const input = { q: "x" };
    expect(kbSearchKey(input)).toEqual(["kb", "search", input]);
    expect(kbSearchKey(null)).toEqual(["kb", "search", null]);
  });

  it("kbDocumentKey incluye el uc_id", () => {
    expect(kbDocumentKey("UC-9")).toEqual(["kb", "document", "UC-9"]);
  });

  it("kbRelatedKey incluye dominio y uc_id excluido", () => {
    expect(kbRelatedKey("rendering-and-publishing", "UC-1")).toEqual([
      "kb",
      "related",
      "rendering-and-publishing",
      "UC-1",
    ]);
  });
});

describe("relatedDocuments", () => {
  it("excluye el documento actual de los relacionados", () => {
    const docs = [
      { uc_id: "UC-1", title: "A" },
      { uc_id: "UC-2", title: "B" },
      { uc_id: "UC-3", title: "C" },
    ];
    expect(relatedDocuments(docs, "UC-2").map((d) => d.uc_id)).toEqual(["UC-1", "UC-3"]);
  });

  it("sin duplicar el propio incluso si aparece varias veces", () => {
    const docs = [
      { uc_id: "UC-2", title: "B" },
      { uc_id: "UC-2", title: "B" },
    ];
    expect(relatedDocuments(docs, "UC-2")).toEqual([]);
  });
});
