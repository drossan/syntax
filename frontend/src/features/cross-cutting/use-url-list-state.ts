"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

import { readListState, writeListState, type ListState } from "@/lib/list-state";

/**
 * Sincroniza el estado de un listado (página + filtros/orden) con la query string. **Inicializa** desde
 * la URL (el listado es compartible por enlace y sobrevive a la recarga) y **escribe** cada cambio con
 * `router.replace`. Mantiene estado interno para re-renderizar de inmediato. Reutilizable por bandeja
 * (07), cola (13), KB (16), dashboard (19).
 *
 * @returns `[state, setState]` — estado actual y su actualizador (también refleja en la URL).
 */
export function useUrlListState(): [ListState, (next: ListState) => void] {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [state, setLocal] = useState<ListState>(() =>
    readListState(new URLSearchParams(searchParams.toString())),
  );

  const setState = useCallback(
    (next: ListState) => {
      setLocal(next);
      const query = writeListState(next);
      router.replace(query ? `${pathname}?${query}` : pathname);
    },
    [router, pathname],
  );

  return [state, setState];
}
