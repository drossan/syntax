# Session log — frontend-helpdesk-core-11 (Adjuntos — solo visualización)

## 2026-08-13 — arranque
- Gate TDD: `status: active`; depends_on [09] en `done`; rama del plan. Baseline 150 tests.

### Gap de contrato (reconocido, una frase de alcance)
- El contrato v0.1.0 **solo** define `POST /messages/{id}/attachments` (subida, fuera de alcance) — **no** hay `GET` para listar adjuntos ni un campo URL de descarga en el schema `Attachment` (solo `id, message_id, filename, content_type, size_bytes`). Además `Message` no embebe adjuntos.
- **Consecuencia**: el componente view-only se entrega completo y testeado por props; su integración en el detalle muestra el **estado vacío** hasta que el backend exponga un GET de adjuntos (bloqueado en backend). El href de descarga apunta a una ruta convencional `…/attachments/{id}` documentada como pendiente (stub de storage, ya declarado en el plan M2). No se inventa un símbolo de código; es un href placeholder etiquetado.

### Decisiones de diseño
- Lógica pura `.ts` (mutación): `attachments.ts` → `formatFileSize(bytes)` (humano: B/KB/MB) + `attachmentDownloadHref(attachment, apiBase)`.
- Presentación `.tsx`: `ticket-attachments.tsx` (lista nombre/tipo/tamaño + enlace descarga + estado vacío; **sin** control de subida). Integrado en `ticket-detail.tsx`.

## 2026-08-13 — cierre
- **Nuevos**: `src/features/tickets/{attachments.ts, ticket-attachments.tsx}` + tests. **Modificados**: `ticket-detail.tsx` (+`<TicketAttachments attachments={[]} />`), `messages/{es,en}.json` (namespace `attachments`).
- **Tests (salida real)**: `pnpm test` → **158 passed / 33 files**; typecheck limpio; lint `No issues found`.
- **Mutación**: Stryker sobre `attachments.ts` → **95.65% ≥ 80** (1 no-cov = fallback `?? ""` del id, código defensivo no ejercido).
- **Fact-checker** (sonnet): **9/9 VERIFICADO** (incluye la confirmación del gap de contrato).
- **Qué falta y por qué**: la lista de adjuntos en el detalle está **vacía** hasta que el backend exponga un `GET` de adjuntos (contrato v0.1.0 no lo tiene) y una URL de descarga real; el componente ya está listo por props. Subida diferida (M2). **Tiempo real**: ~40min.
