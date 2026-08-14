import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth, type AuthApiClient } from "@/features/auth/auth-context";
import type { components } from "@/types/api";

type ApprovalTask = components["schemas"]["ApprovalTask"];

/**
 * Fábrica de mutaciones de decisión sobre una aprobación. En éxito invalida la **cola** (`["approvals"]`)
 * —el ítem resuelto desaparece— y la caché del **ticket** (`["ticket"]`) —aprobar/editar transiciona el
 * ticket y publica un mensaje—. No se duplica: approve/edit/reject la reutilizan.
 *
 * @param run Ejecuta la llamada real y devuelve la `ApprovalTask` resultante.
 */
function useApprovalMutation<Vars>(
  run: (client: AuthApiClient, vars: Vars) => Promise<ApprovalTask>,
) {
  const { client } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (vars: Vars) => run(client, vars),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["approvals"] });
      void queryClient.invalidateQueries({ queryKey: ["ticket"] });
    },
  });
}

/** Aprueba el draft tal cual (`POST /approvals/{id}/approve`). Nota-al-humano opcional. */
export function useApproveApproval(approvalId: string) {
  return useApprovalMutation<{ human_note?: string } | undefined>(async (client, vars) => {
    const { data, error } = await client.POST("/approvals/{id}/approve", {
      params: { path: { id: approvalId } },
      body: vars ?? {},
    });
    if (error) throw error;
    return data;
  });
}

/** Edita el draft y aprueba (`POST /approvals/{id}/edit`); publica el texto editado. */
export function useEditApproval(approvalId: string) {
  return useApprovalMutation<{ final_body: string; human_note?: string }>(async (client, vars) => {
    const { data, error } = await client.POST("/approvals/{id}/edit", {
      params: { path: { id: approvalId } },
      body: vars,
    });
    if (error) throw error;
    return data;
  });
}

/** Rechaza el draft (`POST /approvals/{id}/reject`) con nota-al-humano obligatoria. */
export function useRejectApproval(approvalId: string) {
  return useApprovalMutation<{ human_note: string }>(async (client, vars) => {
    const { data, error } = await client.POST("/approvals/{id}/reject", {
      params: { path: { id: approvalId } },
      body: vars,
    });
    if (error) throw error;
    return data;
  });
}
