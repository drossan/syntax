import { useCallback, useMemo, useSyncExternalStore } from "react";

/** Clave de localStorage para las visitas por ticket (derivación cliente del "leído"). */
const STORAGE_KEY = "syntax:ticket-visits";

const listeners = new Set<() => void>();

/** Lee el JSON crudo de visitas de localStorage (tolerante a datos corruptos / SSR). */
function readRaw(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "{}";
  } catch {
    return "{}";
  }
}

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

/**
 * Store cliente de "visitas" a tickets para derivar el estado **no leído** (el contrato no lo expone
 * server-side). Usa `useSyncExternalStore` (lint-clean + sin mismatch de hidratación: el snapshot de
 * servidor es vacío). `markVisited` sella la visita al abrir el detalle y notifica a los suscriptores.
 */
export function useTicketReads() {
  const raw = useSyncExternalStore(
    subscribe,
    readRaw,
    () => "{}",
  );
  const visits = useMemo<Record<string, string>>(() => {
    try {
      return JSON.parse(raw) as Record<string, string>;
    } catch {
      return {};
    }
  }, [raw]);

  const markVisited = useCallback((ticketId: string) => {
    let current: Record<string, string> = {};
    try {
      current = JSON.parse(readRaw()) as Record<string, string>;
    } catch {
      current = {};
    }
    const next = { ...current, [ticketId]: new Date().toISOString() };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    for (const listener of listeners) listener();
  }, []);

  return { visits, markVisited };
}
