import { KbDocument } from "@/features/kb/kb-document";
import { RequireCapability } from "@/features/rbac/can";

/** Documento de la KB por `uc_id`. Ruta dinámica (Next 16: `params` es Promise). Protegida por `kb.read`. */
export default async function KbDocumentPage({ params }: { params: Promise<{ uc_id: string }> }) {
  const { uc_id } = await params;
  return (
    <RequireCapability capability="kb.read">
      <KbDocument ucId={uc_id} />
    </RequireCapability>
  );
}
