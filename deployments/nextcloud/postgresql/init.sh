#!/usr/bin/env bash
set -euo pipefail
# POSTGRES_USER intentionally remains postgres: the application is not a superuser.
export NEXTCLOUD_DB_PASSWORD
NEXTCLOUD_DB_PASSWORD="$(cat /secrets/db-password)"
psql --username postgres --dbname postgres --no-psqlrc --set ON_ERROR_STOP=1 <<'SQL'
\getenv app_password NEXTCLOUD_DB_PASSWORD
CREATE ROLE nextcloud LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
CREATE DATABASE nextcloud OWNER nextcloud ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE nextcloud FROM PUBLIC;
SQL
unset NEXTCLOUD_DB_PASSWORD
