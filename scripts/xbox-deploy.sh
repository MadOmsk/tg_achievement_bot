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
#   xbox-deploy catalog [--dry-run]
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
# `catalog` carries the games catalog from the test server to prod (owner,
# 2026-10-28: the octopus assembles it on the test server): export from
# test.db with the test bot stopped for a moment, then replace prod's
# catalog with it (scripts/catalog_transfer.py, which backs bot.db up first)
# and bring in `catalog/`, with prod stopped. `--dry-run` does all of it on
# a copy of bot.db instead and touches prod not at all. Both databases must
# be at the same migration, or nothing starts.
#
# Install on the server:
#   install -m 0755 scripts/xbox-deploy.sh /usr/local/bin/xbox-deploy
#   echo 'deploy ALL=(root) NOPASSWD: /usr/local/bin/xbox-deploy' \
#       > /etc/sudoers.d/xbox-deploy && chmod 0440 /etc/sudoers.d/xbox-deploy

set -euo pipefail

MODE="${1:?usage: xbox-deploy test|prod [spa.tgz] | xbox-deploy catalog [--dry-run]}"

RUN_AS=botsvc
PROD_DIR=/opt/xbox_achievement_bot
TEST_DIR=/opt/xbox_bot_test
# Pre-catalog copies of bot.db kept beside it (200 MB each).
KEEP_CATALOG_BACKUPS=2

say() { echo "==> $*"; }
fail() {
  echo "!! $*" >&2
  exit 1
}

# One run at a time, whatever it is: a test deploy, a prod deploy and a
# catalog transfer all stop and start bots on this one box, and CI's
# concurrency groups only keep each workflow from overlapping with itself.
exec 9>/run/xbox-deploy.lock
flock -w 1800 9 || fail "another xbox-deploy is still running"

# Bots this run stopped, started again whatever happens: a failure between
# a stop and its start must never leave a bot down.
STOPPED=()
WORK=""
on_exit() {
  local rc=$?
  local service
  for service in "${STOPPED[@]}"; do
    echo "!! starting $service again after a failure" >&2
    systemctl start "$service" || true
  done
  if [ -n "$WORK" ]; then
    rm -rf -- "$WORK"
  fi
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
copy_db() {
  sudo -u "$RUN_AS" .venv/bin/python - "$1" "$2" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
source = sqlite3.connect(src)
target = sqlite3.connect(dst)
source.backup(target)
target.close()
source.close()
PY
}

# Run as botsvc, never root: a root-owned -wal or -shm beside a database
# locks its bot out of it.
migration() {
  sudo -u "$RUN_AS" sqlite3 "file:$1?mode=ro" "SELECT MAX(version) FROM schema_migrations"
}

deploy() {
  local target="$1" spa_archive="${2:-}"
  local app_dir service branch db web_root keep_backups
  case "$target" in
    prod)
      app_dir=$PROD_DIR
      service=xbox-bot
      branch=main
      db=data/bot.db
      web_root=/var/www/xbox-mini
      keep_backups=8
      ;;
    test)
      app_dir=$TEST_DIR
      service=xbox-bot-test
      branch=prerelease
      db=data/test.db
      web_root=/var/www/xbox-mini-test
      keep_backups=5
      ;;
  esac

  cd "$app_dir"

  say "$target: backing up $db"
  sudo -u "$RUN_AS" mkdir -p data/backups
  local backup
  backup="data/backups/$(basename "$db" .db)-$(date -u +%Y%m%d-%H%M%S).db"
  copy_db "$db" "$backup"
  say "backup: $backup"

  # Only the newest backups are kept (owner, 2026-10-23: every deploy's copy,
  # kept forever, had filled the disk to 96%). Only this script's own copies
  # (<db>-YYYYMMDD-HHMMSS.db) are pruned; a copy named by hand stays.
  # shellcheck disable=SC2012  # names this script and catalog_transfer chose
  ls -1t data/backups |
    { grep -E "^$(basename "$db" .db)-[0-9]{8}-[0-9]{6}\.db$" || true; } |
    tail -n +$((keep_backups + 1)) |
    while read -r old; do
      sudo -u "$RUN_AS" rm -f -- "data/backups/$old"
      say "pruned old backup: $old"
    done

  local before_pyproject
  before_pyproject="$(sha256sum pyproject.toml | cut -d' ' -f1)"

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
  if [ -f scripts/xbox-deploy.sh ]; then
    install -m 0755 scripts/xbox-deploy.sh /usr/local/bin/xbox-deploy
  fi

  if [ "$(sha256sum pyproject.toml | cut -d' ' -f1)" != "$before_pyproject" ]; then
    say "pyproject.toml changed — reinstalling dependencies"
    sudo -u "$RUN_AS" .venv/bin/pip install -q -e .
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
    sudo -u "$RUN_AS" .venv/bin/python -X utf8 -m scripts.catalog_files import --db "$db" ||
      catalog_ok=0
  fi
  start_bot "$service" || exit 1
  if [ "$catalog_ok" = 0 ]; then
    fail "the bot is up, but catalog/ was not brought in"
  fi
  say "$target deployed"
}

catalog() {
  local dry_run=0
  case "${1:-}" in
    "") ;;
    --dry-run) dry_run=1 ;;
    *)
      echo "usage: xbox-deploy catalog [--dry-run]" >&2
      exit 2
      ;;
  esac

  local test_db="$TEST_DIR/data/test.db" prod_db="$PROD_DIR/data/bot.db"
  local test_at prod_at
  test_at="$(migration "$test_db")"
  prod_at="$(migration "$prod_db")"
  if [ -z "$test_at" ] || [ -z "$prod_at" ]; then
    fail "could not read the databases' migrations"
  fi
  if [ "$test_at" != "$prod_at" ]; then
    fail "migrations differ: test.db is at $test_at, bot.db at $prod_at;" \
      "deploy so both run the same migrations first. Nothing was changed."
  fi
  say "both databases at migration $test_at"

  WORK="$(mktemp -d /var/tmp/xbox-catalog.XXXXXX)"
  chown "$RUN_AS:$RUN_AS" "$WORK"
  local file="$WORK/catalog.db"

  # A moment's stop for a catalog that holds still while it is copied.
  cd "$TEST_DIR"
  stop_bot xbox-bot-test
  # The octopus's queue is each server's own work: prod keeps its own.
  sudo -u "$RUN_AS" .venv/bin/python -X utf8 -m scripts.catalog_transfer export \
    --db data/test.db --out "$file" --except octopus_queue
  start_bot xbox-bot-test || exit 1

  cd "$PROD_DIR"
  if [ "$dry_run" = 1 ]; then
    # The whole transfer, rehearsed on a copy of bot.db: the import's own
    # dry run writes and rolls back inside the live file, which would stall
    # the running bot. Prod is neither stopped nor written.
    local copy="$WORK/bot.db"
    say "dry run: rehearsing on a copy of bot.db"
    copy_db data/bot.db "$copy"
    sudo -u "$RUN_AS" .venv/bin/python -X utf8 -m scripts.catalog_transfer import \
      --db "$copy" --file "$file"
    sudo -u "$RUN_AS" .venv/bin/python -X utf8 -m scripts.catalog_files import --db "$copy"
    say "dry run done: prod was not touched"
    return 0
  fi

  stop_bot xbox-bot
  sudo -u "$RUN_AS" .venv/bin/python -X utf8 -m scripts.catalog_transfer import \
    --db data/bot.db --file "$file"
  sudo -u "$RUN_AS" .venv/bin/python -X utf8 -m scripts.catalog_files import --db data/bot.db
  start_bot xbox-bot || exit 1

  # catalog_transfer's own copies (bot-pre-catalog-YYYYMMDD-HHMMSS.db),
  # the newest kept.
  # shellcheck disable=SC2012  # names this script and catalog_transfer chose
  ls -1t data |
    { grep -E '^bot-pre-catalog-[0-9]{8}-[0-9]{6}\.db$' || true; } |
    tail -n +$((KEEP_CATALOG_BACKUPS + 1)) |
    while read -r old; do
      rm -f -- "data/$old"
      say "pruned old catalog backup: $old"
    done
  say "catalog carried from the test server to prod"
}

case "$MODE" in
  test | prod) deploy "$MODE" "${2:-}" ;;
  catalog) catalog "${2:-}" ;;
  *)
    echo "unknown mode: $MODE (expected test, prod or catalog)" >&2
    exit 2
    ;;
esac
