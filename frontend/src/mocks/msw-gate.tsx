"use client";

import { useEffect, useState, type ReactNode } from "react";

/** ¿Está MSW habilitado en el navegador? (dev/e2e). */
const MSW_ENABLED = process.env.NEXT_PUBLIC_ENABLE_MSW === "true";

/**
 * Promesa **singleton** de arranque del worker: se resuelve una sola vez aunque el efecto se monte dos
 * veces (React Strict Mode en dev), evitando el error "network already enabled" de un doble `start()`.
 */
let startPromise: Promise<unknown> | null = null;
function ensureWorkerStarted(): Promise<unknown> {
  if (!startPromise) {
    startPromise = import("./browser").then(({ worker }) =>
      worker.start({ onUnhandledRequest: "bypass" }),
    );
  }
  return startPromise;
}

/**
 * Arranca el worker de MSW **antes** de renderizar la app cuando `NEXT_PUBLIC_ENABLE_MSW=true`
 * (desarrollo / smokes e2e), para que ninguna petición temprana escape al backend real. En producción
 * (flag desactivado) es un passthrough inmediato y el worker ni se importa (el bundle no incluye MSW).
 *
 * @param children Árbol de la aplicación.
 */
export function MswGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(!MSW_ENABLED);

  useEffect(() => {
    if (!MSW_ENABLED) return;
    let active = true;
    void ensureWorkerStarted().then(() => {
      if (active) setReady(true);
    });
    return () => {
      active = false;
    };
  }, []);

  if (!ready) return null;
  return <>{children}</>;
}
