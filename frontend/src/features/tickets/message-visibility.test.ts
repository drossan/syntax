import { describe, expect, it } from "vitest";

import type { components } from "@/types/api";

import { filterByVisibility, prepareThread, sortChronologically } from "./message-visibility";

type Message = components["schemas"]["Message"];

function msg(over: Partial<Message>): Message {
  return {
    id: "m",
    ticket_id: "t",
    author_id: null,
    visibility: "public",
    is_ai_draft: false,
    body: "cuerpo",
    created_at: "2026-08-13T10:00:00Z",
    ...over,
  };
}

const pub = msg({ id: "p", visibility: "public", body: "Mensaje público" });
const internal = msg({ id: "i", visibility: "internal", body: "Nota interna" });

/** Filtro de visibilidad (defensa en profundidad) y orden cronológico del hilo. */
describe("filterByVisibility", () => {
  it("un sujeto sin acceso interno solo ve los mensajes públicos", () => {
    expect(filterByVisibility([pub, internal], false)).toEqual([pub]);
  });

  it("un sujeto con acceso interno ve públicos e internos", () => {
    expect(filterByVisibility([pub, internal], true)).toEqual([pub, internal]);
  });

  it("descarta la nota interna aunque venga en el payload (el cliente no confía en el server)", () => {
    expect(filterByVisibility([internal], false)).toEqual([]);
  });
});

describe("sortChronologically", () => {
  it("ordena por created_at ascendente sin mutar el array original", () => {
    const later = msg({ id: "b", created_at: "2026-08-13T12:00:00Z" });
    const earlier = msg({ id: "a", created_at: "2026-08-13T09:00:00Z" });
    const input = [later, earlier];
    const sorted = sortChronologically(input);
    expect(sorted.map((m) => m.id)).toEqual(["a", "b"]);
    expect(input.map((m) => m.id)).toEqual(["b", "a"]);
  });

  it("trata una fecha ausente como la más temprana sin romper el orden", () => {
    const dated = msg({ id: "a", created_at: "2026-08-13T09:00:00Z" });
    const noDate = msg({ id: "z", created_at: undefined });
    expect(sortChronologically([dated, noDate]).map((m) => m.id)).toEqual(["z", "a"]);
  });
});

describe("prepareThread", () => {
  it("filtra por visibilidad y luego ordena cronológicamente", () => {
    const laterInternal = msg({ id: "i", visibility: "internal", created_at: "2026-08-13T12:00:00Z" });
    const earlierPublic = msg({ id: "p", visibility: "public", created_at: "2026-08-13T09:00:00Z" });
    expect(prepareThread([laterInternal, earlierPublic], false).map((m) => m.id)).toEqual(["p"]);
    expect(prepareThread([laterInternal, earlierPublic], true).map((m) => m.id)).toEqual(["p", "i"]);
  });
});
