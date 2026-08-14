import { describe, expect, it } from "vitest";

import { attachmentDownloadHref, formatFileSize } from "./attachments";

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

describe("attachmentDownloadHref", () => {
  it("construye la ruta de descarga con el id del adjunto", () => {
    expect(attachmentDownloadHref({ id: "att-1" }, "https://api.test")).toBe(
      "https://api.test/api/v1/attachments/att-1",
    );
  });

  it("usa ruta relativa si no se da base", () => {
    expect(attachmentDownloadHref({ id: "att-2" })).toBe("/api/v1/attachments/att-2");
  });
});
