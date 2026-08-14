import { KbSearch } from "@/features/kb/kb-search";
import { RequireCapability } from "@/features/rbac/can";

/** Base de conocimiento (buscar). Protegida por `kb.read`. */
export default function KbPage() {
  return (
    <RequireCapability capability="kb.read">
      <KbSearch />
    </RequireCapability>
  );
}
