"""app.domain.ports.clock — puerto de reloj (tiempo inyectable).

GUIÓN (→ tarea 10)
------------------
Interfaz mínima para obtener el "ahora" (UTC) de forma **inyectable** → hace testeables las reglas que
dependen del tiempo (SLA ``sla_due``, expiración de ``AuthToken``/``RefreshSession``, escalado del
scheduler 18) sin depender del reloj real ni de ``Date.now``.

  - ``now() -> datetime`` (timezone-aware, UTC).

Adaptador real en ``app.infra`` (reloj del sistema); en tests se inyecta uno fijo.
Anti-patrón: llamar a ``datetime.now()`` directamente dentro de la lógica de negocio (no determinista).
"""
