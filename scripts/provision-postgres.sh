#!/usr/bin/env bash
# The bots' PostgreSQL (#234): settings, roles, the database, its schemas, and
# DATABASE_URL in each bot's env file. Run as root from a copy of the
# repository; provision.sh runs it, and it is safe to run again:
#
#   sudo bash scripts/provision-postgres.sh [database]
#
# A role's password is made here once, and lives only in that bot's env file;
# it is never printed. Given another database's name (a rehearsal), it makes
# that database the same way and leaves the env files alone.
#
# It starts no bot: a bot reads the database once its code does (the switch).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DATABASE="${1:-unlocked}"
CONF_DIR=/etc/postgresql/16/main/conf.d

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }

psql_admin() {
  (cd / && sudo -u postgres psql -v ON_ERROR_STOP=1 -q "$@")
}

if ! cmp -s "$REPO/deploy/postgresql/unlocked.conf" "$CONF_DIR/unlocked.conf"; then
  install -m 644 -o postgres -g postgres "$REPO/deploy/postgresql/unlocked.conf" "$CONF_DIR/"
  # shared_buffers takes a restart.
  systemctl restart postgresql
fi
systemctl enable --quiet postgresql

for role in unlocked_games unlocked_prod unlocked_test; do
  psql_admin -d postgres <<SQL
SELECT 'CREATE ROLE $role' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$role') \gexec
SQL
done
# CREATEDB: a dry run of scripts/reparse_store_payloads.py works on a copy.
psql_admin -d postgres <<'SQL'
ALTER ROLE unlocked_games NOLOGIN;
ALTER ROLE unlocked_prod LOGIN CREATEDB;
ALTER ROLE unlocked_test LOGIN CREATEDB;
ALTER ROLE unlocked_prod SET search_path = prod, games;
ALTER ROLE unlocked_test SET search_path = test, games;
GRANT unlocked_games TO unlocked_prod, unlocked_test;
SQL

# C.UTF-8: the bytes' order, as SQLite sorted, and lower() that knows Cyrillic.
if [ -z "$(psql_admin -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '$DATABASE'")" ]; then
  psql_admin -d postgres -c \
    "CREATE DATABASE \"$DATABASE\" TEMPLATE template0 ENCODING 'UTF8' LOCALE 'C.UTF-8'"
fi
psql_admin -d "$DATABASE" -v database="$DATABASE" < "$REPO/deploy/postgresql/setup.sql"

connect_bot() {  # env_file role schema
  local env_file="$1" role="$2" schema="$3" password
  [ -f "$env_file" ] || { echo "no $env_file: $role left without a password" >&2; return 0; }
  grep -q '^DATABASE_URL=' "$env_file" && return 0
  password="$(openssl rand -hex 24)"
  # On standard input, so it shows in no process list.
  psql_admin -d postgres <<SQL
ALTER ROLE $role PASSWORD '$password';
SQL
  {
    echo
    echo "# PostgreSQL (#234)."
    echo "DATABASE_URL=postgresql://$role:$password@localhost:5432/unlocked"
    echo "DATABASE_SCHEMA=$schema"
  } >> "$env_file"
  echo "$role: password made, kept in $env_file"
}

if [ "$DATABASE" = unlocked ]; then
  connect_bot /opt/xbox_achievement_bot/.env unlocked_prod prod
  connect_bot /opt/xbox_bot_test/.env.test unlocked_test test
fi
