#!/usr/bin/env bash
# The deploy itself, run on the server by GitHub Actions (#4).
#
# Canonical copy lives here so it is reviewed and versioned like everything
# else; the server runs a copy at /usr/local/bin/xbox-deploy, installed once
# and re-installed when this file changes. It is the *only* thing the deploy
# user is allowed to run as root (see `sudoers` at the bottom of this
# comment), so the blast radius of the CI key is "can deploy what is already
# in the repository", not "root on the box".
#
#   xbox-deploy test|prod [/path/to/spa.tgz]
#
# Both targets do the same five things, in this order and for these reasons:
#
#   1. back up the database — every time, not only when a migration ships.
#      Migrations here are forward-only and a destructive one cannot be
#      undone without a kept copy (CLAUDE.md, Operations). 38 MB and a
#      second, against a deploy that is now automatic and unattended.
#   2. fast-forward the checkout — never a merge, never a reset: if the
#      branch and the server have diverged, a human needs to look.
#   3. reinstall dependencies only when pyproject.toml actually changed.
#   4. unpack the Mini App, when the caller brought one.
#   5. restart, then *verify* — an exit code from systemctl says the unit
#      was asked to start, not that the bot came up. The log line does.
#
# Install on the server:
#   install -m 0755 scripts/xbox-deploy.sh /usr/local/bin/xbox-deploy
#   echo 'deploy ALL=(root) NOPASSWD: /usr/local/bin/xbox-deploy' \
#       > /etc/sudoers.d/xbox-deploy && chmod 0440 /etc/sudoers.d/xbox-deploy

set -euo pipefail

TARGET="${1:?usage: xbox-deploy test|prod [spa.tgz]}"
SPA_ARCHIVE="${2:-}"

case "$TARGET" in
  prod)
    APP_DIR=/opt/xbox_achievement_bot
    SERVICE=xbox-bot
    BRANCH=main
    DB=data/bot.db
    WEB_ROOT=/var/www/xbox-mini
    ;;
  test)
    APP_DIR=/opt/xbox_bot_test
    SERVICE=xbox-bot-test
    BRANCH=prerelease
    DB=data/test.db
    WEB_ROOT=/var/www/xbox-mini-test
    ;;
  *)
    echo "unknown target: $TARGET (expected test or prod)" >&2
    exit 2
    ;;
esac

RUN_AS=botsvc
say() { echo "==> $*"; }

cd "$APP_DIR"

say "$TARGET: backing up $DB"
sudo -u "$RUN_AS" mkdir -p data/backups
BACKUP="data/backups/$(basename "$DB" .db)-$(date -u +%Y%m%d-%H%M%S).db"
# sqlite's own backup(), never cp: these run in WAL mode and a plain copy of
# one can come back malformed (CLAUDE.md, Operations).
sudo -u "$RUN_AS" .venv/bin/python - "$DB" "$BACKUP" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
source = sqlite3.connect(src)
target = sqlite3.connect(dst)
source.backup(target)
target.close()
source.close()
PY
say "backup: $BACKUP"

BEFORE_PYPROJECT="$(sha256sum pyproject.toml | cut -d' ' -f1)"

say "fetching origin"
# Every branch, not just this one: `bot/version.py` counts C from the merge
# base with main, so a stale origin/main on the test checkout makes the test
# bot report a version dozens of commits wide (seen: v1.2.42.050 on a
# checkout identical to main). One extra ref, no extra round trip.
# --tags as well: the version counts production's releases from the newest
# release tag, and a server that never fetched one would report 0 forever.
sudo -u "$RUN_AS" git fetch origin --tags
# --ff-only on purpose: a checkout that has drifted from its branch is a
# question for a person, not something to paper over with a merge commit
# made by a robot at three in the morning.
sudo -u "$RUN_AS" git merge --ff-only "origin/$BRANCH"
say "now at $(sudo -u "$RUN_AS" git log --oneline -1)"

if [ -f scripts/xbox-deploy.sh ]; then
  install -m 0755 scripts/xbox-deploy.sh /usr/local/bin/xbox-deploy
fi

if [ "$(sha256sum pyproject.toml | cut -d' ' -f1)" != "$BEFORE_PYPROJECT" ]; then
  say "pyproject.toml changed — reinstalling dependencies"
  sudo -u "$RUN_AS" .venv/bin/pip install -q -e .
else
  say "dependencies unchanged"
fi

if [ -n "$SPA_ARCHIVE" ] && [ -f "$SPA_ARCHIVE" ]; then
  say "unpacking the Mini App into $WEB_ROOT"
  mkdir -p "$WEB_ROOT"
  # Replaced wholesale rather than merged: Vite hashes asset names, so an
  # old build's files would linger forever and the directory would only ever
  # grow.
  rm -rf "${WEB_ROOT:?}"/*
  tar -xzf "$SPA_ARCHIVE" -C "$WEB_ROOT"
  chown -R www-data:www-data "$WEB_ROOT"
  rm -f "$SPA_ARCHIVE"
fi

say "restarting $SERVICE"
# Noted *before* the restart, and every check below is bounded by it. A
# relative window ('90 seconds ago') matches the previous deploy's own
# "is up" line whenever two deploys land close together — which reports
# success for a restart that may not have happened yet, and would report it
# for one that failed outright.
SINCE="$(date +'%Y-%m-%d %H:%M:%S')"
systemctl restart "$SERVICE"

# systemctl returning 0 means the unit was asked to start. Whether the bot
# actually came up is a different question, and the answer is in its log:
# a database newer than the code refuses to start (#56), a bad migration
# stops the process, and either would otherwise look like a green deploy.
say "waiting for it to come up"
for _ in $(seq 1 30); do
  if journalctl -u "$SERVICE" --since "$SINCE" --no-pager | grep 'is up (' >/dev/null 2>&1; then
    journalctl -u "$SERVICE" --since "$SINCE" --no-pager | grep 'is up (' | tail -1
    say "$TARGET deployed"
    exit 0
  fi
  if ! systemctl is-active --quiet "$SERVICE"; then
    echo "!! $SERVICE is not running" >&2
    journalctl -u "$SERVICE" --since "$SINCE" --no-pager | tail -30 >&2
    exit 1
  fi
  sleep 2
done

echo "!! $SERVICE did not report itself up within 60s" >&2
journalctl -u "$SERVICE" --since "$SINCE" --no-pager | tail -30 >&2
exit 1
