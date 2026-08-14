import { NextResponse, type NextRequest } from "next/server";

/** Prefijos de ruta accesibles sin sesión (login y flujos de contraseña/invitación). */
const PUBLIC_PREFIXES = ["/login", "/password"];

/**
 * Redirect UX por presencia de la cookie de refresh. **No es control de seguridad** (eso lo hace la
 * API): solo evita mostrar el shell autenticado a quien no tiene sesión. Sin cookie de refresh en una
 * ruta protegida → redirige a `/login`.
 *
 * En Next.js 16 la convención `middleware` pasó a llamarse `proxy` (misma funcionalidad).
 */
export function proxy(request: NextRequest): NextResponse {
  const hasRefreshCookie = request.cookies.has("refresh_token");
  const { pathname } = request.nextUrl;
  const isPublic = PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));

  if (!hasRefreshCookie && !isPublic) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.).*)"],
};
