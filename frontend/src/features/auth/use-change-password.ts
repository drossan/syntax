import { useMutation } from "@tanstack/react-query";

import { useAuth } from "./auth-context";

/** Cambia la contraseña del usuario autenticado (`POST /auth/password/change`). */
export function useChangePassword() {
  const { client } = useAuth();

  return useMutation({
    mutationFn: async (body: { current_password: string; new_password: string }) => {
      const { error } = await client.POST("/auth/password/change", { body });
      if (error) throw error;
    },
  });
}
