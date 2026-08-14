import { SetPasswordForm } from "@/features/auth/set-password-form";

/** Página para fijar una nueva contraseña con el token de reset (`?token=...`). */
export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const token = typeof params.token === "string" ? params.token : "";

  return (
    <main className="mx-auto flex min-h-full w-full max-w-sm flex-col justify-center gap-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Nueva contraseña</h1>
      <SetPasswordForm token={token} mode="reset" />
    </main>
  );
}
