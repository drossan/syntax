import { LoginForm } from "@/features/auth/login-form";

/** Página de login (route group `(auth)`). Chrome estático + formulario cliente. */
export default function LoginPage() {
  return (
    <main className="mx-auto flex min-h-full w-full max-w-sm flex-col justify-center gap-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Iniciar sesión</h1>
      <LoginForm />
    </main>
  );
}
