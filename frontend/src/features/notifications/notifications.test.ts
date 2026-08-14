import { describe, expect, it } from "vitest";

import { notificationFixture } from "@/mocks/fixtures";

import { unreadCount } from "./notifications";

describe("unreadCount", () => {
  it("cuenta las notificaciones con read_at null", () => {
    const items = [
      notificationFixture({ id: "a", read_at: null }),
      notificationFixture({ id: "b", read_at: "2026-08-13T11:00:00Z" }),
      notificationFixture({ id: "c", read_at: null }),
    ];
    expect(unreadCount(items)).toBe(2);
  });

  it("es 0 cuando todas están leídas o no hay ninguna", () => {
    expect(unreadCount([notificationFixture({ read_at: "2026-08-13T11:00:00Z" })])).toBe(0);
    expect(unreadCount([])).toBe(0);
  });
});
