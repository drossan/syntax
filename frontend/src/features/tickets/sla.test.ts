import { describe, expect, it } from "vitest";

import { SLA_IMMINENT_WINDOW_MS, slaLevel } from "./sla";

const NOW = Date.parse("2026-08-13T12:00:00Z");

/**
 * Indicador de SLA (solo visual; el cómputo/escalado es del backend, task 18).
 * Escenario Gherkin: "Indicador de SLA vencido" + fronteras del refuerzo.
 */
describe("slaLevel", () => {
  it("sin fecha de SLA no muestra indicador", () => {
    expect(slaLevel(null, NOW)).toBe("none");
    expect(slaLevel(undefined, NOW)).toBe("none");
  });

  it("una fecha no parseable no muestra indicador (no rompe la fila)", () => {
    expect(slaLevel("no-es-una-fecha", NOW)).toBe("none");
  });

  it("un SLA en el pasado está vencido", () => {
    expect(slaLevel("2026-08-13T11:59:59Z", NOW)).toBe("overdue");
  });

  it("un SLA justo en el instante actual está vencido (frontera <= 0)", () => {
    expect(slaLevel("2026-08-13T12:00:00Z", NOW)).toBe("overdue");
  });

  it("un SLA dentro de la ventana de aviso es inminente", () => {
    const due = new Date(NOW + SLA_IMMINENT_WINDOW_MS - 1000).toISOString();
    expect(slaLevel(due, NOW)).toBe("imminent");
  });

  it("un SLA justo en el borde de la ventana sigue siendo inminente (frontera == ventana)", () => {
    const due = new Date(NOW + SLA_IMMINENT_WINDOW_MS).toISOString();
    expect(slaLevel(due, NOW)).toBe("imminent");
  });

  it("un SLA más allá de la ventana es normal", () => {
    const due = new Date(NOW + SLA_IMMINENT_WINDOW_MS + 1000).toISOString();
    expect(slaLevel(due, NOW)).toBe("normal");
  });

  it("respeta una ventana de aviso personalizada", () => {
    const due = new Date(NOW + 30 * 60 * 1000).toISOString();
    expect(slaLevel(due, NOW, 10 * 60 * 1000)).toBe("normal");
    expect(slaLevel(due, NOW, 60 * 60 * 1000)).toBe("imminent");
  });
});
