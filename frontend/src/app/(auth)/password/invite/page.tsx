import { SetPasswordForm } from "@/features/auth/set-password-form";

/** Página para aceptar una invitación fijando la contraseña inicial (`?token=...`). */
export default async function AcceptInvitePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const token = typeof params.token === "string" ? params.token : "";

  return (
    <main className="mx-auto flex min-h-full w-full max-w-sm flex-col justify-center gap-6 p-8">
      <div className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold tracking-tight">Activa tu cuenta</h1>
        <p className="text-sm text-muted-foreground">Elige una contraseña para empezar.</p>
      </div>
      <SetPasswordForm token={token} mode="invite" />
    </main>
  );
}
