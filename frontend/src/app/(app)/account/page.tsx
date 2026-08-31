import { ChangePasswordForm } from "@/features/auth/change-password-form";

/** Cuenta del sujeto autenticado: cambiar contraseña. Sin gating de capacidad — cualquiera puede. */
export default function AccountPage() {
  return (
    <section className="flex flex-col gap-6 p-4">
      <ChangePasswordForm />
    </section>
  );
}
