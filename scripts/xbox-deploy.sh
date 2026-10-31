#!/usr/bin/env bash
# The deploy itself, run on the server by GitHub Actions (#4).
#
# Canonical copy lives here so it is reviewed and versioned like everything
# else; the server runs a copy at /usr/local/bin/xbox-deploy, installed once
# and re-installed by every deploy from its checkout. It is the *only* thing
# the deploy user is allowed to run as root (see `sudoers` at the bottom of
# this comment), so the blast radius of the CI key is "can deploy what is
# already in the repository", not "root on the box".
#
#   xbox-deploy test|prod [/path/to/spa.tgz]
#   xbox-deploy backup
#
# A deploy (test or prod) does these things, in this order and for these
# reasons:
#
#   1. back up the database — every time, not only when a migration ships.
#      Migrations here are forward-only and a destructive one cannot be
#      undone without a kept copy (CLAUDE.md, Operations).
#   2. fast-forward the checkout — never a merge, never a reset: if the
#      branch and the server have diverged, a human needs to look.
#   3. reinstall dependencies only when pyproject.toml actually changed.
#   4. unpack the Mini App, when the caller brought one.
#   5. stop the bot, bring the catalog's labels and weights in from
#      `catalog/` (scripts/catalog_files.py: it compares, so an unchanged
#      folder writes nothing), start it, then *verify* — an exit code from
#      systemctl says the unit was asked to start, not that the bot came up.
#      The log line does.
#
# `backup` is the daily copy (deploy/systemd/unlocked-backup.timer): every bot
# already on PostgreSQL, pruned with the deploys' copies.
#
# While the bots move to PostgreSQL (#234), a bot whose schema has no tables yet
# is still on SQLite, and is backed up and brought in as before.
#
# Install on the server:
#   install -m 0755 scripts/xbox-deploy.sh /usr/local/bin/xbox-deploy
#   echo 'deploy ALL=(root) NOPASSWD: /usr/local/bin/xbox-deploy' \
#       > /etc/sudoers.d/xbox-deploy && chmod 0440 /etc/sudoers.d/xbox-deploy

set -euo pipefail

MODE="${1:?usage: xbox-deploy test|prod [spa.tgz] | xbox-deploy backup}"

RUN_AS=botsvc
PROD_DIR=/opt/xbox_achievement_bot
TEST_DIR=/opt/xbox_bot_test
DATABASE=unlocked
# Which edition of this script this is. While the bots are on different code a
# deploy would otherwise install the older checkout's copy over a newer one
# (#234): one without this line counts as 0, and is never installed over it.
DEPLOY_SCRIPT_EDITION=1

say() { echo "==> $*"; }
fail() {
  echo "!! $*" >&2
  exit 1
}

# One run at a time, whatever it is: a test deploy, a prod deploy and a
# backup all stop bots or read them on this one box, and CI's
# concurrency groups only keep each workflow from overlapping with itself.
exec 9>/run/xbox-deploy.lock
flock -w 1800 9 || fail "another xbox-deploy is still running"

# Bots this run stopped, started again whatever happens: a failure between
# a stop and its start must never leave a bot down.
STOPPED=()
on_exit() {
  local rc=$?
  local service
  for service in "${STOPPED[@]}"; do
    echo "!! starting $service again after a failure" >&2
    systemctl start "$service" || true
  done
  exit "$rc"
}
trap on_exit EXIT

stop_bot() {
  say "stopping $1"
  systemctl stop "$1"
  STOPPED+=("$1")
}

# Starts the unit and waits for the bot's own "is up (v…)" line. The time is
# noted *before* the start and every check is bounded by it: a relative
# window ('90 seconds ago') matches the previous run's own line whenever two
# land close together, reporting success for a start that may not have
# happened. systemctl returning 0 means the unit was asked to start; a
# database newer than the code refuses to start (#56), a bad migration stops
# the process, and either would otherwise look green.
start_bot() {
  local service="$1" since kept=() s
  since="$(date +'%Y-%m-%d %H:%M:%S')"
  say "starting $service"
  systemctl restart "$service"
  for s in "${STOPPED[@]}"; do
    if [ "$s" != "$service" ]; then
      kept+=("$s")
    fi
  done
  STOPPED=("${kept[@]}")
  say "waiting for $service to come up"
  for _ in $(seq 1 30); do
    if journalctl -u "$service" --since "$since" --no-pager | grep 'is up (' >/dev/null 2>&1; then
      journalctl -u "$service" --since "$since" --no-pager | grep 'is up (' | tail -1
      return 0
    fi
    if ! systemctl is-active --quiet "$service"; then
      echo "!! $service is not running" >&2
      journalctl -u "$service" --since "$since" --no-pager | tail -30 >&2
      return 1
    fi
    sleep 2
  done
  echo "!! $service did not report itself up within 60s" >&2
  journalctl -u "$service" --since "$since" --no-pager | tail -30 >&2
  return 1
}

# sqlite's own backup(), never cp: these run in WAL mode and a plain copy of
# one can come back malformed (CLAUDE.md, Operations). Run from a checkout.
# A database keeping its games in a file of its own (#229) is copied with it
# (`<copy>.games.db`, the copy naming it); a checkout from before has no
# `bot.db.files`, and its database is one file.
copy_db() {
  sudo -u "$RUN_AS" .venv/bin/python - "$1" "$2" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
try:
    from bot.db import files
except ImportError:
    source = sqlite3.connect(src)
    target = sqlite3.connect(dst)
    source.backup(target)
    target.close()
    source.close()
else:
    files.backup(src, dst)
PY
}

# A database that cannot be asked is an error, never "not on PostgreSQL yet": that
# would back up a stale SQLite file and report success.
schema_has_tables() {
  local found
  found="$(cd / && sudo -u postgres psql -v ON_ERROR_STOP=1 -d "$DATABASE" -Atc \
    "SELECT 1 FROM information_schema.tables WHERE table_schema = '$1' LIMIT 1")" ||
    fail "PostgreSQL cannot be asked about schema $1"
  [ -n "$found" ]
}

# pg_dump of a bot's schema and the catalog, as postgres: no password on a
# command line. Written beside its name first, so a dump cut short is no copy.
dump_schema() {  # schema target
  if ! (cd / && sudo -u postgres pg_dump --format=custom --schema="$1" --schema=games "$DATABASE") |
    sudo -u "$RUN_AS" tee "$2.part" >/dev/null; then
    sudo -u "$RUN_AS" rm -f -- "$2.part"
    return 1
  fi
  sudo -u "$RUN_AS" mv "$2.part" "$2"
}

# Only the newest are kept (owner, 2026-10-23: every deploy's copy, kept forever,
# had filled the disk to 96%), and only this script's own, named
# <name>-YYYYMMDD-HHMMSS; a copy named by hand stays. A SQLite copy's games file
# (<copy>.games.db) goes with it.
prune_backups() {  # name keep
  # shellcheck disable=SC2012  # names this script chose
  ls -1t data/backups |
    { grep -E "^$1-[0-9]{8}-[0-9]{6}\.(db|dump)$" || true; } |
    tail -n +$(($2 + 1)) |
    while read -r old; do
      sudo -u "$RUN_AS" rm -f -- "data/backups/$old" "data/backups/${old%.db}.games.db"
      say "pruned old backup: $old"
    done
}

# One bot's failure does not cost the other its copy; the run still ends red.
backup_all() {
  local app_dir schema keep failed=0
  while read -r app_dir schema keep; do
    if ! schema_has_tables "$schema"; then
      say "$schema: not on PostgreSQL yet"
      continue
    fi
    cd "$app_dir"
    sudo -u "$RUN_AS" mkdir -p data/backups
    if ! dump_schema "$schema" "data/backups/$schema-$(date -u +%Y%m%d-%H%M%S).dump"; then
      echo "!! $schema: the dump failed" >&2
      failed=1
      continue
    fi
    prune_backups "$schema" "$keep"
    say "$schema: backed up"
  done <<EOF
$PROD_DIR prod 8
$TEST_DIR test 5
EOF
  [ "$failed" = 0 ] || fail "a backup failed"
}

deploy() {
  local target="$1" spa_archive="${2:-}"
  local app_dir service branch db schema env_file web_root keep_backups
  case "$target" in
    prod)
      app_dir=$PROD_DIR
      service=xbox-bot
      branch=main
      db=data/bot.db
      schema="prod"
      env_file=$PROD_DIR/.env
      web_root=/var/www/xbox-mini
      keep_backups=8
      ;;
    test)
      app_dir=$TEST_DIR
      service=xbox-bot-test
      branch=prerelease
      db=data/test.db
      schema="test"
      env_file=$TEST_DIR/.env.test
      web_root=/var/www/xbox-mini-test
      keep_backups=5
      ;;
  esac

  cd "$app_dir"

  sudo -u "$RUN_AS" mkdir -p data/backups
  local backup name
  if schema_has_tables "$schema"; then
    name=$schema
    backup="data/backups/$name-$(date -u +%Y%m%d-%H%M%S).dump"
    say "$target: backing up schemas $schema and games"
    dump_schema "$schema" "$backup" || fail "the dump failed"
  else
    name="$(basename "$db" .db)"
    backup="data/backups/$name-$(date -u +%Y%m%d-%H%M%S).db"
    say "$target: backing up $db"
    copy_db "$db" "$backup"
  fi
  say "backup: $backup"
  prune_backups "$name" "$keep_backups"

  say "fetching origin"
  # Every branch, not just this one: `bot/version.py` counts C from the merge
  # base with main, so a stale origin/main on the test checkout makes the
  # test bot report a version dozens of commits wide. --prune: a renamed or
  # deleted branch must not linger as a stale origin/* ref. --tags: the
  # version counts production's releases from the newest release tag.
  sudo -u "$RUN_AS" git fetch --prune origin --tags
  # --ff-only on purpose: a checkout that has drifted from its branch is a
  # question for a person, not something to paper over with a merge commit
  # made by a robot at three in the morning.
  sudo -u "$RUN_AS" git merge --ff-only "origin/$branch"
  say "now at $(sudo -u "$RUN_AS" git log --oneline -1)"

  # The running copy keeps reading its old file (install writes a new one),
  # so what changes here takes effect from the next run.
  # Only forward: see DEPLOY_SCRIPT_EDITION.
  local edition
  edition="$(sed -n 's/^DEPLOY_SCRIPT_EDITION=//p' scripts/xbox-deploy.sh 2>/dev/null || true)"
  if [ "${edition:-0}" -ge "$DEPLOY_SCRIPT_EDITION" ]; then
    install -m 0755 scripts/xbox-deploy.sh /usr/local/bin/xbox-deploy
  fi

  # Against what was last installed, not what this run's merge changed: a failed
  # install is tried again by the next run, which sees no change in the checkout.
  local wanted
  wanted="$(sha256sum pyproject.toml | cut -d' ' -f1)"
  if [ "$(cat .venv/.installed-pyproject 2>/dev/null || true)" != "$wanted" ]; then
    say "pyproject.toml changed — reinstalling dependencies"
    sudo -u "$RUN_AS" .venv/bin/pip install -q -e .
    echo "$wanted" | sudo -u "$RUN_AS" tee .venv/.installed-pyproject >/dev/null
  else
    say "dependencies unchanged"
  fi

  if [ -n "$spa_archive" ] && [ -f "$spa_archive" ]; then
    say "unpacking the Mini App into $web_root"
    mkdir -p "$web_root"
    # Replaced wholesale rather than merged: Vite hashes asset names, so an
    # old build's files would linger forever and the directory would only
    # ever grow.
    rm -rf "${web_root:?}"/*
    tar -xzf "$spa_archive" -C "$web_root"
    chown -R www-data:www-data "$web_root"
    rm -f "$spa_archive"
  fi

  stop_bot "$service"
  # The labels and weights trained once and kept in git (`catalog/`) come in
  # with the code. A failure here still starts the bot — the code is
  # deployed — but turns the deploy red.
  local catalog_ok=1
  if [ -f scripts/catalog_files.py ]; then
    say "bringing in catalog/ (labels and weights)"
    # The checkout's own way of naming its database, whichever it now is.
    local where=(--db "$db")
    if [ -f bot/db/postgres.py ]; then
      where=(--schema "$schema")
    fi
    # The unit names the env file; a script run here has to be told.
    sudo -u "$RUN_AS" env BOT_ENV_FILE="$env_file" \
      .venv/bin/python -X utf8 -m scripts.catalog_files import "${where[@]}" ||
      catalog_ok=0
  fi
  start_bot "$service" || exit 1
  if [ "$catalog_ok" = 0 ]; then
    fail "the bot is up, but catalog/ was not brought in"
  fi
  say "$target deployed"
}

case "$MODE" in
  test | prod) deploy "$MODE" "${2:-}" ;;
  backup) backup_all ;;
  *)
    echo "unknown mode: $MODE (expected test, prod or backup)" >&2
    exit 2
    ;;
esac
