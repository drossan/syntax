import { afterEach, describe, expect, it, vi } from "vitest";

import { formatFileSize, triggerBrowserDownload } from "./attachments";

/** Formato humano de tamaño y URL de descarga del adjunto. */
describe("formatFileSize", () => {
  it("muestra bytes por debajo de 1 KB", () => {
    expect(formatFileSize(0)).toBe("0 B");
    expect(formatFileSize(512)).toBe("512 B");
    expect(formatFileSize(1023)).toBe("1023 B");
  });

  it("muestra KB entre 1 KB y 1 MB", () => {
    expect(formatFileSize(1024)).toBe("1.0 KB");
    expect(formatFileSize(1536)).toBe("1.5 KB");
  });

  it("muestra MB a partir de 1 MB", () => {
    expect(formatFileSize(1024 * 1024)).toBe("1.0 MB");
    expect(formatFileSize(1024 * 1024 * 3)).toBe("3.0 MB");
  });

  it("un tamaño desconocido (undefined) se muestra como guion", () => {
    expect(formatFileSize(undefined)).toBe("—");
  });
});

describe("triggerBrowserDownload", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("crea una URL de objeto, la clica con un <a> desechable, y la libera", () => {
    const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:test-url");
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    const blob = new Blob(["contenido"], { type: "text/plain" });

    triggerBrowserDownload(blob, "informe.pdf");

    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:test-url");
    // El <a> desechable no queda colgado en el DOM tras la descarga.
    expect(document.querySelectorAll("a[download]")).toHaveLength(0);
  });
});
