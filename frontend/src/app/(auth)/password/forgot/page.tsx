import { ForgotPasswordForm } from "@/features/auth/forgot-password-form";

/** Página "olvidé mi contraseña" (route group `(auth)`). */
export default function ForgotPasswordPage() {
  return (
    <main className="mx-auto flex min-h-full w-full max-w-sm flex-col justify-center gap-6 p-8">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Restablecer contraseña</h1>
        <p className="text-sm text-muted-foreground">
          Introduce tu email y te enviaremos instrucciones para restablecerla.
        </p>
      </div>
      <ForgotPasswordForm />
    </main>
  );
}
