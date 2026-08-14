import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import esMessages from "../../../messages/es.json";

import { OfflineBanner } from "./offline-banner";

function renderBanner(queryClient: QueryClient) {
  return render(
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="es" messages={esMessages} timeZone="Europe/Madrid">
        <OfflineBanner />
      </NextIntlClientProvider>
    </QueryClientProvider>,
  );
}

describe("OfflineBanner", () => {
  it("no muestra nada con conexión; avisa al perderla y reintenta lecturas al recuperarla", () => {
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    renderBanner(queryClient);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/sin conexión/i);

    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(invalidateSpy).toHaveBeenCalled();
  });
});
