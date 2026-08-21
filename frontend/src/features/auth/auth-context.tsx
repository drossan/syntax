"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import type { components } from "@/types/api";

import { createAuthClient } from "./auth-client";

type User = components["schemas"]["User"];
type Me = components["schemas"]["Me"];
type Capability = NonNullable<Me["capabilities"]>[number];
type Problem = components["schemas"]["Problem"];
type TokenResponse = components["schemas"]["TokenResponse"];
type TenantChoice = components["schemas"]["TenantChoice"];

/** Cliente HTTP autenticado (openapi-fetch tipado con el contrato). */
export type AuthApiClient = ReturnType<typeof createAuthClient>["client"];

/** Estado de la sesión: en carga (bootstrap), autenticada o no. */
export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

/**
 * Login con 2+ membresías `active`: el paso 1 no autentica todavía — hay que elegir uno de
 * `tenants` y canjearlo con {@link AuthContextValue.selectTenant} usando el mismo `identityToken`.
 */
export interface TenantSelectionChallenge {
  identityToken: string;
  tenants: TenantChoice[];
}

/** Valor expuesto por el contexto de autenticación. */
export interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  /** Tenant de la sesión activa (`Me.active_tenant_id`); `null` hasta que resuelve. */
  sessionTenantId: string | null;
  capabilities: Capability[];
  /**
   * Tenants con membership `active` del usuario (`Me.available_tenants`), incluido el tenant de la
   * sesión activa. Longitud 1 → nadie ve el switcher; 2+ → cualquier usuario puede cambiar de tenant.
   */
  availableTenants: TenantChoice[];
  /** Cliente HTTP autenticado para el data-fetching de las features (TanStack Query). */
  client: AuthApiClient;
  /**
   * Inicia sesión. Con 1 tenant, completa la sesión y devuelve `{}`. Con 2+ membresías `active`,
   * devuelve `{ tenantSelection }` sin autenticar todavía — hay que llamar a {@link selectTenant}.
   * Devuelve `{ error }` (problem+json) si las credenciales fallan.
   */
  login: (
    email: string,
    password: string,
  ) => Promise<{ error?: Problem; tenantSelection?: TenantSelectionChallenge }>;
  /**
   * Canjea un `identityToken` (de {@link TenantSelectionChallenge}) por la sesión real del tenant
   * elegido. En error (401/422) devuelve `{ error }` sin invalidar el `identityToken`: puede
   * reintentarse con el mismo token mientras siga vigente.
   */
  selectTenant: (identityToken: string, tenantId: string) => Promise<{ error?: Problem }>;
  /**
   * Cambia de tenant con la sesión ya autenticada (`POST /auth/switch-tenant`). En error (401/403)
   * devuelve `{ error }` sin tocar el estado de sesión (sigue en el tenant anterior); en éxito,
   * actualiza `sessionTenantId`/`user`/`capabilities`/`availableTenants` igual que un login directo.
   */
  switchTenant: (tenantId: string) => Promise<{ error?: Problem }>;
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
  const [availableTenants, setAvailableTenants] = useState<TenantChoice[]>([]);

  // Cliente + sesión estables durante toda la vida del provider (lazy init, una sola vez).
  const [{ client, session }] = useState(() =>
    createAuthClient({
      baseUrl,
      onLogout: () => {
        setStatus("unauthenticated");
        setUser(null);
        setSessionTenantId(null);
        setCapabilities([]);
        setAvailableTenants([]);
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
        setCapabilities(data.capabilities);
        setAvailableTenants(data.available_tenants);
        setStatus("authenticated");
      } else {
        setStatus("unauthenticated");
      }
    })();
    return () => {
      active = false;
    };
  }, [client, session]);

  /**
   * Completa la sesión a partir de un `TokenResponse` ya válido (login directo, `selectTenant` o
   * `switchTenant`): fija el access token y confirma la identidad vía `GET /auth/me`. Si `/auth/me`
   * falla pese al token válido, NO marca `authenticated` — limpia también cualquier resto de sesión
   * previa (relevante para `switchTenant`, que se llama ya autenticado) y devuelve `{ error }` sin
   * dejar un estado a medias (Gherkin: «Fallo al confirmar la identidad…»).
   */
  const completeSession = async (tokens: TokenResponse): Promise<{ error?: Problem }> => {
    session.setToken(tokens.access_token);
    const { data, error } = await client.GET("/auth/me", {});
    if (!data) {
      session.setToken(null);
      setStatus("unauthenticated");
      setUser(null);
      setSessionTenantId(null);
      setCapabilities([]);
      setAvailableTenants([]);
      return { error };
    }
    setUser(data.user);
    setSessionTenantId(data.active_tenant_id);
    setCapabilities(data.capabilities);
    setAvailableTenants(data.available_tenants);
    setStatus("authenticated");
    return {};
  };

  const login: AuthContextValue["login"] = async (email, password) => {
    const { data, error } = await client.POST("/auth/login", { body: { email, password } });
    if (error) return { error };

    if ("identity_token" in data) {
      // Identidad con 2+ tenants: hay que elegir uno con `selectTenant` (sin autenticar todavía).
      return { tenantSelection: { identityToken: data.identity_token, tenants: data.tenants } };
    }

    return completeSession(data);
  };

  const selectTenant: AuthContextValue["selectTenant"] = async (identityToken, tenantId) => {
    const { data, error } = await client.POST("/auth/select-tenant", {
      body: { identity_token: identityToken, tenant_id: tenantId },
    });
    if (error) return { error };
    return completeSession(data);
  };

  const switchTenant: AuthContextValue["switchTenant"] = async (tenantId) => {
    const { data, error } = await client.POST("/auth/switch-tenant", {
      body: { tenant_id: tenantId },
    });
    if (error) return { error };
    return completeSession(data);
  };

  const logout: AuthContextValue["logout"] = async () => {
    await client.POST("/auth/logout", {}).catch(() => undefined);
    session.setToken(null);
    queryClient.clear();
    setStatus("unauthenticated");
    setUser(null);
    setSessionTenantId(null);
    setCapabilities([]);
    setAvailableTenants([]);
  };

  return (
    <AuthContext.Provider
      value={{
        status,
        user,
        sessionTenantId,
        capabilities,
        availableTenants,
        client,
        login,
        selectTenant,
        switchTenant,
        logout,
      }}
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
