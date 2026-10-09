#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${POD_UID:?}" "${PGHOST:?}" "${PGDATABASE:?}" "${PGUSER:?}" "${PGPASSWORD:?}"
case "$POD_UID" in *[!a-zA-Z0-9-]*|'') exit 1;; esac
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="/work/${stamp}-${POD_UID}"
mkdir "$backup_dir"
pg_dump --no-password --format=custom --file="$backup_dir/nextcloud.dump"
test -s "$backup_dir/nextcloud.dump"
pg_restore --list "$backup_dir/nextcloud.dump" >/dev/null
# Decode the full archive without executing SQL or contacting any restore database.
pg_restore --file=/dev/null "$backup_dir/nextcloud.dump"
(cd "$backup_dir" && sha256sum nextcloud.dump > SHA256SUMS)
{
  printf 'created_utc=%s\nengine=postgresql\ndatabase=nextcloud\n' "$stamp"
  pg_dump --version
  printf 'image=%s\n' "$POSTGRES_IMAGE"
} > "$backup_dir/metadata.txt"
printf 'Validated database dump: %s bytes\n' "$(wc -c < "$backup_dir/nextcloud.dump")"
