import { describe, expect, it } from "vitest";

import type { components } from "@/types/api";

import { buildTimeline } from "./timeline";

type Message = components["schemas"]["Message"];

function msg(over: Partial<Message>): Message {
  return {
    id: "m",
    ticket_id: "t",
    author_id: "u1",
    visibility: "public",
    is_ai_draft: false,
    body: "x",
    created_at: "2026-08-13T10:00:00Z",
    ...over,
  };
}

/** El timeline se deriva del hilo (respeta visibilidad y orden cronológico). */
describe("buildTimeline", () => {
  it("ordena los eventos cronológicamente y conserva actor y fecha", () => {
    const later = msg({ id: "b", author_id: "u2", created_at: "2026-08-13T12:00:00Z" });
    const earlier = msg({ id: "a", author_id: "u1", created_at: "2026-08-13T09:00:00Z" });
    const events = buildTimeline([later, earlier], true);
    expect(events.map((e) => e.id)).toEqual(["a", "b"]);
    expect(events[0]).toMatchObject({ actor: "u1", at: "2026-08-13T09:00:00Z" });
  });

  it("distingue el borrador de IA del mensaje normal", () => {
    const ai = msg({ id: "ai", is_ai_draft: true });
    const normal = msg({ id: "n", is_ai_draft: false });
    const events = buildTimeline([ai, normal], true);
    expect(events.find((e) => e.id === "ai")?.kind).toBe("ai_draft");
    expect(events.find((e) => e.id === "n")?.kind).toBe("message");
  });

  it("respeta la visibilidad: un cliente no ve eventos de notas internas", () => {
    const pub = msg({ id: "p", visibility: "public" });
    const internal = msg({ id: "i", visibility: "internal" });
    expect(buildTimeline([pub, internal], false).map((e) => e.id)).toEqual(["p"]);
    expect(buildTimeline([pub, internal], true).map((e) => e.id)).toEqual(["p", "i"]);
  });

  it("un mensaje sin autor deja actor null", () => {
    expect(buildTimeline([msg({ id: "s", author_id: null })], true)[0]?.actor).toBeNull();
  });

  it("un mensaje sin id ni fecha degrada a cadenas vacías sin romper", () => {
    const event = buildTimeline([msg({ id: undefined, created_at: undefined })], true)[0];
    expect(event?.id).toBe("");
    expect(event?.at).toBe("");
  });
});
