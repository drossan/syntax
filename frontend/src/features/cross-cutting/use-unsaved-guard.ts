import { useEffect } from "react";

/**
 * Pide confirmación del navegador al **abandonar la página** (recarga/cierre/nav dura) mientras haya
 * cambios sin guardar (`beforeunload`). Solo engancha el handler cuando `dirty` es `true`.
 *
 * Limitación (App Router): la navegación soft entre rutas no dispara `beforeunload`; este guard cubre
 * recarga/cierre/nav externa. El guard de nav soft se abordará si el router expone un hook estable.
 *
 * @param dirty Si el formulario tiene cambios sin guardar.
 */
export function useUnsavedGuard(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
}
