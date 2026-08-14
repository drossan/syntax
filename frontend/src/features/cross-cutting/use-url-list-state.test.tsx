import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const replace = vi.fn();
const searchState = { value: "status=pending&page=2" };

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/tickets",
  useSearchParams: () => new URLSearchParams(searchState.value),
}));

import { useUrlListState } from "./use-url-list-state";

describe("useUrlListState", () => {
  it("inicializa el estado desde la URL (compartible / sobrevive a recarga)", () => {
    searchState.value = "status=pending&page=2";
    const { result } = renderHook(() => useUrlListState());
    expect(result.current[0]).toStrictEqual({ page: 2, status: "pending" });
  });

  it("al actualizar refleja el estado en la URL con router.replace y actualiza el estado interno", () => {
    searchState.value = "";
    replace.mockClear();
    const { result } = renderHook(() => useUrlListState());
    expect(result.current[0]).toStrictEqual({ page: 1 });

    act(() => result.current[1]({ page: 3, status: "open" }));

    expect(replace).toHaveBeenCalledWith("/tickets?page=3&status=open");
    expect(result.current[0]).toStrictEqual({ page: 3, status: "open" });
  });

  it("una página 1 sin filtros limpia la query (ruta sin query string)", () => {
    searchState.value = "";
    replace.mockClear();
    const { result } = renderHook(() => useUrlListState());
    act(() => result.current[1]({ page: 1 }));
    expect(replace).toHaveBeenCalledWith("/tickets");
  });
});
