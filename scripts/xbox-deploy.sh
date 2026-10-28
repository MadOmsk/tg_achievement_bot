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
#   xbox-deploy games split|join|leave [--dry-run]
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
# `games` moves the bots onto one games database (#229; owner, 2026-10-28),
# with each bot it touches stopped (scripts/games_db.py, which copies the
# database into backups/ first):
#   split  the test server's catalog becomes the shared file ($GAMES_DB);
#   join   prod takes the shared file, adding what only it knew of its lists;
#   leave  both copy the shared catalog back and part, for a rework of the
#          games database that cannot be shared (CLAUDE.md).
# `--dry-run` does it on copies in a temporary folder, no bot stopped.
#
# Install on the server:
#   install -m 0755 scripts/xbox-deploy.sh /usr/local/bin/xbox-deploy
#   echo 'deploy ALL=(root) NOPASSWD: /usr/local/bin/xbox-deploy' \
#       > /etc/sudoers.d/xbox-deploy && chmod 0440 /etc/sudoers.d/xbox-deploy

set -euo pipefail

MODE="${1:?usage: xbox-deploy test|prod [spa.tgz] | xbox-deploy games split|join|leave [--dry-run]}"

RUN_AS=botsvc
PROD_DIR=/opt/xbox_achievement_bot
TEST_DIR=/opt/xbox_bot_test
# The games database both bots attach (#229).
GAMES_DIR=/srv/unlocked-games
GAMES_DB=$GAMES_DIR/games.db

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
  # A copy's games file (<copy>.games.db) goes with it.
  # shellcheck disable=SC2012  # names this script chose
  ls -1t data/backups |
    { grep -E "^$(basename "$db" .db)-[0-9]{8}-[0-9]{6}\.db$" || true; } |
    tail -n +$((keep_backups + 1)) |
    while read -r old; do
      sudo -u "$RUN_AS" rm -f -- "data/backups/$old" "data/backups/${old%.db}.games.db"
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

games() {
  local command="${1:-}" dry_run="${2:-}"
  case "$command" in
    split | join | leave) ;;
    *)
      echo "usage: xbox-deploy games split|join|leave [--dry-run]" >&2
      exit 2
      ;;
  esac
  case "$dry_run" in
    "" | --dry-run) ;;
    *)
      echo "usage: xbox-deploy games split|join|leave [--dry-run]" >&2
      exit 2
      ;;
  esac
  mkdir -p "$GAMES_DIR"
  chown "$RUN_AS:$RUN_AS" "$GAMES_DIR"

  # app_dir, service and database of each bot the command touches.
  local -a bots
  case "$command" in
    split) bots=("$TEST_DIR xbox-bot-test data/test.db") ;;
    join) bots=("$PROD_DIR xbox-bot data/bot.db") ;;
    leave) bots=("$TEST_DIR xbox-bot-test data/test.db" "$PROD_DIR xbox-bot data/bot.db") ;;
  esac
  local bot app_dir service db
  for bot in "${bots[@]}"; do
    read -r app_dir service db <<<"$bot"
    cd "$app_dir"
    if [ -n "$dry_run" ]; then
      sudo -u "$RUN_AS" .venv/bin/python -X utf8 -m scripts.games_db "$command"         --db "$db" --games "$GAMES_DB" --dry-run
      continue
    fi
    stop_bot "$service"
    sudo -u "$RUN_AS" .venv/bin/python -X utf8 -m scripts.games_db "$command"       --db "$db" --games "$GAMES_DB"
    start_bot "$service" || exit 1
  done
  say "games $command${dry_run:+ (dry run)} done"
}

case "$MODE" in
  test | prod) deploy "$MODE" "${2:-}" ;;
  games) games "${2:-}" "${3:-}" ;;
  *)
    echo "unknown mode: $MODE (expected test, prod or games)" >&2
    exit 2
    ;;
esac
