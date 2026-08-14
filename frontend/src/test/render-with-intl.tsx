import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";

import esMessages from "../../messages/es.json";

/**
 * Renderiza un componente de presentación con i18n (locale `es`, timezone fija) sin el stack de sesión.
 * Para componentes puros que solo dependen de next-intl (SLA, timeline, adjuntos…).
 *
 * @param ui Elemento a renderizar.
 */
export function renderWithIntl(ui: ReactElement) {
  return render(
    <NextIntlClientProvider locale="es" messages={esMessages} timeZone="Europe/Madrid">
      {ui}
    </NextIntlClientProvider>,
  );
}
