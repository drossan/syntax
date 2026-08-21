"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import type { components } from "@/types/api";

import { createAuthClient } from "./auth-client";

type User = components["schemas"]["User"];
type Me = components["schemas"]["Me"];
type Capability = NonNullable<Me["capabilities"]>[number];
type Problem = components["schemas"]["Problem"];

/** Cliente HTTP autenticado (openapi-fetch tipado con el contrato). */
export type AuthApiClient = ReturnType<typeof createAuthClient>["client"];

/** Estado de la sesión: en carga (bootstrap), autenticada o no. */
export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

/** Valor expuesto por el contexto de autenticación. */
export interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  /** Tenant de la sesión activa (`Me.active_tenant_id`); `null` hasta que resuelve. */
  sessionTenantId: string | null;
  capabilities: Capability[];
  /** Cliente HTTP autenticado para el data-fetching de las features (TanStack Query). */
  client: AuthApiClient;
  /** Inicia sesión; devuelve `{ error }` (problem+json) si las credenciales fallan. */
  login: (email: string, password: string) => Promise<{ error?: Problem }>;
  /** Cierra la sesión (revoca en servidor, resetea la caché de Query y el estado). */
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Provee la sesión (app client-rendered: el access token vive en memoria). Al montar hace bootstrap
 * vía `/auth/refresh` + `/auth/me`. Debe ir dentro de `QueryClientProvider` (resetea su caché al salir).
 */
export function AuthProvider({ children, baseUrl }: { children: ReactNode; baseUrl?: string }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [sessionTenantId, setSessionTenantId] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<Capability[]>([]);

  // Cliente + sesión estables durante toda la vida del provider (lazy init, una sola vez).
  const [{ client, session }] = useState(() =>
    createAuthClient({
      baseUrl,
      onLogout: () => {
        setStatus("unauthenticated");
        setUser(null);
        setSessionTenantId(null);
        setCapabilities([]);
      },
    }),
  );

  useEffect(() => {
    let active = true;
    void (async () => {
      const refreshed = await session.refresh();
      if (!active) return;
      if (!refreshed) {
        setStatus("unauthenticated");
        return;
      }
      const { data } = await client.GET("/auth/me", {});
      if (!active) return;
      if (data) {
        setUser(data.user);
        setSessionTenantId(data.active_tenant_id);
        setCapabilities(data.capabilities ?? []);
        setStatus("authenticated");
      } else {
        setStatus("unauthenticated");
      }
    })();
    return () => {
      active = false;
    };
  }, [client, session]);

  const login: AuthContextValue["login"] = async (email, password) => {
    const { data, error } = await client.POST("/auth/login", { body: { email, password } });
    if (error) return { error };

    if ("identity_token" in data) {
      // Identidad con 2+ tenants: requiere `POST /auth/select-tenant`, sin pantalla propia todavía.
      return {
        error: {
          type: "about:blank",
          title: "Selección de tenant no disponible",
          status: 501,
          detail: "Tu cuenta pertenece a varios tenants; este cliente aún no soporta elegir uno.",
        },
      };
    }

    session.setToken(data.access_token);
    const me = await client.GET("/auth/me", {});
    if (me.data) {
      setUser(me.data.user);
      setSessionTenantId(me.data.active_tenant_id);
      setCapabilities(me.data.capabilities ?? []);
      setStatus("authenticated");
    }
    return {};
  };

  const logout: AuthContextValue["logout"] = async () => {
    await client.POST("/auth/logout", {}).catch(() => undefined);
    session.setToken(null);
    queryClient.clear();
    setStatus("unauthenticated");
    setUser(null);
    setSessionTenantId(null);
    setCapabilities([]);
  };

  return (
    <AuthContext.Provider
      value={{ status, user, sessionTenantId, capabilities, client, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

/** Accede a la sesión. Lanza si se usa fuera de `<AuthProvider>`. */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}

/** Atajo para la acción de cierre de sesión. */
export function useLogout(): AuthContextValue["logout"] {
  return useAuth().logout;
}
