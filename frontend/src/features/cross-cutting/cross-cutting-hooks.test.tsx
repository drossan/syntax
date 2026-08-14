import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useOnlineStatus } from "./use-online-status";
import { useTicketReads } from "./use-ticket-reads";
import { useUnsavedGuard } from "./use-unsaved-guard";

afterEach(() => {
  localStorage.clear();
});

describe("useOnlineStatus", () => {
  it("refleja la pérdida y recuperación de conexión", () => {
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(true);

    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(result.current).toBe(false);

    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(result.current).toBe(true);
  });
});

describe("useUnsavedGuard", () => {
  function fireBeforeUnload(): Event {
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    return event;
  }

  it("con cambios sin guardar pide confirmación (previene la descarga)", () => {
    renderHook(({ dirty }) => useUnsavedGuard(dirty), { initialProps: { dirty: true } });
    expect(fireBeforeUnload().defaultPrevented).toBe(true);
  });

  it("sin cambios no interfiere en la navegación", () => {
    renderHook(({ dirty }) => useUnsavedGuard(dirty), { initialProps: { dirty: false } });
    expect(fireBeforeUnload().defaultPrevented).toBe(false);
  });

  it("retira el guard al desmontar", () => {
    const { unmount } = renderHook(({ dirty }) => useUnsavedGuard(dirty), { initialProps: { dirty: true } });
    unmount();
    expect(fireBeforeUnload().defaultPrevented).toBe(false);
  });

  it("deja de guardar cuando el formulario vuelve a estar limpio", () => {
    const { rerender } = renderHook(({ dirty }) => useUnsavedGuard(dirty), { initialProps: { dirty: true } });
    rerender({ dirty: false });
    expect(fireBeforeUnload().defaultPrevented).toBe(false);
  });
});

describe("useTicketReads", () => {
  it("marca un ticket como visitado y lo persiste", () => {
    const { result } = renderHook(() => useTicketReads());
    act(() => result.current.markVisited("t-1"));
    expect(result.current.visits["t-1"]).toBeTruthy();
    expect(localStorage.getItem("syntax:ticket-visits")).toContain("t-1");
  });

  it("lee las visitas existentes de localStorage", () => {
    localStorage.setItem("syntax:ticket-visits", JSON.stringify({ prev: "2026-08-13T10:00:00Z" }));
    const { result } = renderHook(() => useTicketReads());
    expect(result.current.visits.prev).toBe("2026-08-13T10:00:00Z");
  });

  it("datos corruptos en localStorage → visitas vacías (sin romper)", () => {
    localStorage.setItem("syntax:ticket-visits", "no-es-json");
    const { result } = renderHook(() => useTicketReads());
    expect(result.current.visits).toStrictEqual({});
  });

  it("marcar una visita preserva las visitas previas", () => {
    localStorage.setItem("syntax:ticket-visits", JSON.stringify({ a: "2026-08-13T10:00:00Z" }));
    const { result } = renderHook(() => useTicketReads());
    act(() => result.current.markVisited("b"));
    expect(result.current.visits.a).toBe("2026-08-13T10:00:00Z");
    expect(result.current.visits.b).toBeTruthy();
  });
});
