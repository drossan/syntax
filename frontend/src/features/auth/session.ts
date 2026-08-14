/** Dependencias de la sesión: cómo renovar y qué hacer al cerrar. */
export interface SessionDeps {
  /** Ejecuta `POST /auth/refresh` y devuelve el nuevo access token, o `null` si falla (reuse-detection). */
  refreshFn: () => Promise<string | null>;
  /** Se invoca cuando el refresh falla de forma terminal (sesión cerrada). */
  onLogout?: () => void;
}

/**
 * Dueña del access token (en memoria) y del ciclo de renovación con **single-flight**: N llamadas
 * concurrentes a `refresh()` disparan una sola ejecución de `refreshFn`; todas resuelven con su
 * resultado. Un `refreshFn` que devuelve `null` (reuse-detection) limpia el token e invoca `onLogout`.
 */
export class SessionManager {
  /** Access token vigente (en memoria; nunca en storage persistente). */
  token: string | null = null;

  private refreshing: Promise<boolean> | null = null;

  constructor(private readonly deps: SessionDeps) {}

  /** Fija (o limpia) el access token. */
  setToken(token: string | null): void {
    this.token = token;
  }

  /**
   * Renueva el access token. Single-flight: si ya hay una renovación en curso, devuelve su misma
   * promesa en lugar de lanzar otra.
   *
   * @returns `true` si se obtuvo un token nuevo; `false` si el refresh falló (sesión cerrada).
   */
  refresh(): Promise<boolean> {
    this.refreshing ??= this.runRefresh();
    return this.refreshing;
  }

  private async runRefresh(): Promise<boolean> {
    try {
      const newToken = await this.deps.refreshFn();
      if (newToken) {
        this.token = newToken;
        return true;
      }
      this.token = null;
      this.deps.onLogout?.();
      return false;
    } finally {
      this.refreshing = null;
    }
  }
}
