import { describe, expect, it } from "vitest";

import { isUnread } from "./unread";

describe("isUnread", () => {
  it("nunca visitado → no leído", () => {
    expect(isUnread("2026-08-13T10:00:00Z", undefined)).toBe(true);
  });

  it("actividad posterior a la última visita → no leído", () => {
    expect(isUnread("2026-08-13T12:00:00Z", "2026-08-13T10:00:00Z")).toBe(true);
  });

  it("sin actividad desde la última visita → leído", () => {
    expect(isUnread("2026-08-13T09:00:00Z", "2026-08-13T10:00:00Z")).toBe(false);
    expect(isUnread("2026-08-13T10:00:00Z", "2026-08-13T10:00:00Z")).toBe(false);
  });

  it("sin fecha de actualización → leído (nada que señalar)", () => {
    expect(isUnread(undefined, "2026-08-13T10:00:00Z")).toBe(false);
  });
});
