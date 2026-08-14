/**
 * Añade un rol al conjunto del usuario sin duplicar (idempotente). No muta el array de entrada.
 *
 * @param current Roles actuales del usuario.
 * @param roleId Rol a añadir.
 */
export function addRole(current: string[], roleId: string): string[] {
  return current.includes(roleId) ? current : [...current, roleId];
}

/**
 * Retira un rol del conjunto del usuario (no-op si no lo tenía).
 *
 * @param current Roles actuales del usuario.
 * @param roleId Rol a retirar.
 */
export function removeRole(current: string[], roleId: string): string[] {
  return current.filter((role) => role !== roleId);
}

/**
 * Un rol de sistema (semilla) es inmutable: se puede asignar pero no editar/borrar (rbac §3).
 *
 * @param kind `kind` del rol (`system` | `tenant`).
 */
export function isSystemRole(kind: string | undefined): boolean {
  return kind === "system";
}
