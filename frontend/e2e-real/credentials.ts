/**
 * Credenciales de los 6 usuarios semilla (`backend/app/infra/db/seed.py`, `DEV_PASSWORD`) — SOLO
 * dev/e2e, nunca producción. `python -m app.infra.db.seed` es idempotente: re-ejecutarlo antes de la
 * suite no duplica nada.
 */
export const DEV_PASSWORD = "DevPassword123!";

export const E2E_USERS = {
  supportAdmin: { email: "support-admin@syntax.local", password: DEV_PASSWORD },
  supportAgent: { email: "support-agent@syntax.local", password: DEV_PASSWORD },
  clientAgent: { email: "client-agent@demo.local", password: DEV_PASSWORD },
  clientViewer: { email: "client-viewer@demo.local", password: DEV_PASSWORD },
} as const;
