import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-context";
import type { components } from "@/types/api";

type UserInvite = components["schemas"]["UserInvite"];
type UserStatus = components["schemas"]["UserStatus"];
type TenantSettings = components["schemas"]["TenantSettings"];

/** Usuarios del tenant del sujeto (`GET /admin/users`; el servidor escopa por sujeto). */
export function useUsers() {
  const { client } = useAuth();
  return useQuery({
    queryKey: ["admin", "users"],
    queryFn: async () => {
      const { data, error } = await client.GET("/admin/users", {});
      if (error) throw error;
      return data.items;
    },
  });
}

/** Catálogo de roles visibles (`GET /admin/roles`) para asignar en la invitación. */
export function useRoles() {
  const { client } = useAuth();
  return useQuery({
    queryKey: ["admin", "roles"],
    queryFn: async () => {
      const { data, error } = await client.GET("/admin/roles", {});
      if (error) throw error;
      return data;
    },
  });
}

/** Crea un tenant (`POST /admin/tenants`); invalida el listado de tenants en éxito. */
export function useCreateTenant() {
  const { client } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { slug: string; name: string }) => {
      const { data, error } = await client.POST("/admin/tenants", { body });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] });
    },
  });
}

/** Ajustes de un tenant (`GET /admin/settings?tenant_id=`) — `auto_approve`/`ai_auto_draft`. */
export function useTenantSettings(tenantId: string) {
  const { client } = useAuth();
  return useQuery({
    queryKey: ["admin", "settings", tenantId],
    queryFn: async () => {
      const { data, error } = await client.GET("/admin/settings", {
        params: { query: { tenant_id: tenantId } },
      });
      if (error) throw error;
      return data;
    },
  });
}

/** Actualiza los ajustes de un tenant (`PATCH /admin/settings?tenant_id=`); invalida esa query. */
export function useUpdateTenantSettings(tenantId: string) {
  const { client } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: TenantSettings) => {
      const { data, error } = await client.PATCH("/admin/settings", {
        params: { query: { tenant_id: tenantId } },
        body,
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "settings", tenantId] });
    },
  });
}

/** Invita a un usuario (`POST /admin/users`); invalida el listado de usuarios en éxito. */
export function useInviteUser() {
  const { client } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: UserInvite) => {
      const { data, error } = await client.POST("/admin/users", { body });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}

/**
 * Actualiza un usuario (`PATCH /admin/users/{id}`): `status` (soft-delete = `disabled`) y/o `roles`
 * (asignación de roles semilla, task 18). Envía solo los campos definidos. Invalida usuarios en éxito.
 */
export function useUpdateUser() {
  const { client } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { id: string; status?: UserStatus; roles?: string[] }) => {
      const body: { status?: UserStatus; roles?: string[] } = {};
      if (vars.status !== undefined) body.status = vars.status;
      if (vars.roles !== undefined) body.roles = vars.roles;
      const { data, error } = await client.PATCH("/admin/users/{id}", {
        params: { path: { id: vars.id } },
        body,
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}
