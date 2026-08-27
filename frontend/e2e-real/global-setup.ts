import { E2E_USERS } from "./credentials";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/**
 * Verifica prerrequisitos ANTES de arrancar los specs — fallar aquí con un mensaje claro es mucho
 * mejor que dejar que 6 specs fallen de forma confusa por un backend caído o sin seeds.
 *
 * NO dispara `python -m app.infra.db.seed` él mismo: invocar un venv de Python desde un
 * `globalSetup` de Node es frágil entre entornos (ruta del venv, SO). En su lugar, confirma que el
 * seed YA corrió (login real del usuario semilla) y lo dice explícito si no.
 */
export default async function globalSetup(): Promise<void> {
  let ready: Response;
  try {
    ready = await fetch(`${API_BASE_URL}/health/ready`);
  } catch (cause) {
    throw new Error(
      `Backend no alcanzable en ${API_BASE_URL} — arráncalo (\`make -C backend run\`, con ` +
        `\`docker compose -f backend/docker-compose.yml up -d db\` primero).`,
      { cause },
    );
  }
  if (!ready.ok) {
    throw new Error(
      `Backend en ${API_BASE_URL} respondió ${ready.status} en /health/ready — la DB no está lista.`,
    );
  }

  const admin = E2E_USERS.supportAdmin;
  const login = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: admin.email, password: admin.password }),
  });
  if (!login.ok) {
    throw new Error(
      `Login del usuario semilla (${admin.email}) falló (${login.status}) — corre ` +
        `\`python -m app.infra.db.seed\` (con PYTHONPATH=. y el venv del backend) antes de \`pnpm e2e:real\`.`,
    );
  }
}
