#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# docker-entrypoint-initdb.d/01-create-app-role.sh
#
# Crea el rol RUNTIME de la app `syntax_app` (NOSUPERUSER NOBYPASSRLS LOGIN) — el rol
# NO-superuser bajo el que corre la API, para que las políticas RLS se apliquen de
# verdad (un superusuario las saltaría). Se ejecuta SOLO en la primera inicialización
# del volumen de datos (comportamiento estándar de la imagen de Postgres).
#
# Idempotente (DO block). La password se fija OUT-OF-BAND desde la variable de entorno
# SYNTAX_APP_PASSWORD (nunca hardcodeada en el fichero) — ADR-0016 / plan M1-M2.
# En prod este paso es un runbook de ops equivalente (el rol se crea fuera de Alembic).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	DO \$\$
	BEGIN
	  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'syntax_app') THEN
	    CREATE ROLE syntax_app NOSUPERUSER NOBYPASSRLS LOGIN;
	  END IF;
	END
	\$\$;
	ALTER ROLE syntax_app PASSWORD '${SYNTAX_APP_PASSWORD:-syntax_app}';
EOSQL
