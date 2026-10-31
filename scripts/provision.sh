#!/usr/bin/env bash
# A fresh Ubuntu 24.04 box made into the bots' server: users, SSH, nginx,
# PostgreSQL, the two checkouts, the units and the deploy script. Run as root
# from a copy of the repository:
#
#   sudo bash scripts/provision.sh /path/to/deploy_authorized_keys
#
# The file holds the public keys the `deploy` user accepts: CI's
# (github-actions-deploy) and the operators'. It is safe to run again: every
# step checks before it changes anything. It never starts a bot — the bots
# start at the cutover, once their databases, .env files and the TLS
# certificate are copied over; until then the old server keeps running them,
# and one BOT_TOKEN must never poll from two servers at once.
#
# SSH moves to port 22022 (keys only, as on the old box). Port 22 stays open
# beside it until `--close-22` is given, after a login on 22022 was checked.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_KEYS="${1:?usage: provision.sh deploy_authorized_keys [--close-22]}"
CLOSE_22="${2:-}"
REPO_URL=https://github.com/MadOmsk/tg_achievement_bot.git

log() { printf '\n== %s\n' "$*"; }

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
[ -s "$DEPLOY_KEYS" ] || { echo "no keys in $DEPLOY_KEYS" >&2; exit 1; }

log "packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -yq
apt-get install -yq \
  nginx certbot python3-certbot-nginx git sqlite3 rsync \
  build-essential python3.12-venv python3.12-dev libjpeg-dev zlib1g-dev \
  postgresql postgresql-contrib unattended-upgrades

log "time zone and swap"
timedatectl set-timezone Etc/UTC
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

log "users"
id botsvc >/dev/null 2>&1 || useradd --create-home --shell /bin/bash botsvc
id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
install -m 600 -o deploy -g deploy "$DEPLOY_KEYS" /home/deploy/.ssh/authorized_keys

log "ssh: keys only, port 22022"
cat > /etc/ssh/sshd_config.d/10-keys-only.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
install -d /etc/systemd/system/ssh.socket.d
if [ "$CLOSE_22" = "--close-22" ]; then
  install -m 644 "$REPO/deploy/systemd/ssh.socket.d/override.conf" \
    /etc/systemd/system/ssh.socket.d/override.conf
else
  # Both ports until a login on 22022 is proved.
  cat > /etc/systemd/system/ssh.socket.d/override.conf <<'EOF'
[Socket]
ListenStream=
ListenStream=0.0.0.0:22
ListenStream=[::]:22
ListenStream=0.0.0.0:22022
ListenStream=[::]:22022
EOF
fi
systemctl daemon-reload
systemctl restart ssh.socket

log "folders"
install -d -o botsvc -g botsvc /srv/unlocked-games /srv/unlocked-media
install -d -o www-data -g www-data /var/www/xbox-mini /var/www/xbox-mini-test

log "checkouts"
checkout() {  # dir branch
  if [ ! -d "$1/.git" ]; then
    install -d -o botsvc -g botsvc "$1"
    sudo -u botsvc git clone --branch "$2" "$REPO_URL" "$1"
  fi
  sudo -u botsvc mkdir -p "$1/data" "$1/logs"
  if [ ! -x "$1/.venv/bin/python" ]; then
    sudo -u botsvc python3.12 -m venv "$1/.venv"
  fi
  # From inside the checkout: pip writes beside the current folder, and the
  # caller's (root's or the admin's) is not botsvc's to write.
  (cd "$1" && sudo -u botsvc .venv/bin/pip install -q --upgrade pip &&
    sudo -u botsvc .venv/bin/pip install -q -e .)
}
checkout /opt/xbox_achievement_bot main
checkout /opt/xbox_bot_test prerelease

log "units (installed, not started)"
install -m 644 "$REPO/deploy/systemd/xbox-bot.service" /etc/systemd/system/
install -m 644 "$REPO/deploy/systemd/xbox-bot-test.service" /etc/systemd/system/
install -d /etc/systemd/system/xbox-bot.service.d
install -m 644 "$REPO/deploy/systemd/xbox-bot.service.d/shared.conf" \
  /etc/systemd/system/xbox-bot.service.d/
systemctl daemon-reload
systemctl disable --now xbox-bot xbox-bot-test 2>/dev/null || true

log "deploy script"
install -m 0755 "$REPO/scripts/xbox-deploy.sh" /usr/local/bin/xbox-deploy
echo 'deploy ALL=(root) NOPASSWD: /usr/local/bin/xbox-deploy' > /etc/sudoers.d/xbox-deploy
chmod 0440 /etc/sudoers.d/xbox-deploy
visudo -cf /etc/sudoers.d/xbox-deploy

log "nginx (sites enabled once the certificate is in place)"
rm -f /etc/nginx/sites-enabled/default
install -m 644 "$REPO/deploy/nginx/xbox-bot.conf" /etc/nginx/sites-available/xbox-bot
install -m 644 "$REPO/deploy/nginx/xbox-mini-test.conf" /etc/nginx/sites-available/xbox-mini-test
if [ -f /etc/letsencrypt/live/xbox.sultanpharm.com/fullchain.pem ]; then
  ln -sf /etc/nginx/sites-available/xbox-bot /etc/nginx/sites-enabled/xbox-bot
  ln -sf /etc/nginx/sites-available/xbox-mini-test /etc/nginx/sites-enabled/xbox-mini-test
fi
# unlocked.how (#237): Cloudflare's origin certificate; its key is made on the
# server and never leaves it (only the CSR goes to Cloudflare).
install -m 644 "$REPO/deploy/nginx/cloudflare-realip.conf" /etc/nginx/snippets/
install -m 644 "$REPO/deploy/nginx/unlocked.conf" /etc/nginx/sites-available/unlocked
if [ -f /etc/ssl/unlocked/origin.pem ] && [ -f /etc/ssl/unlocked/origin.key ]; then
  ln -sf /etc/nginx/sites-available/unlocked /etc/nginx/sites-enabled/unlocked
fi
nginx -t
systemctl reload nginx

log "postgresql (#234)"
bash "$REPO/scripts/provision-postgres.sh"

log "daily backup"
install -m 644 "$REPO/deploy/systemd/unlocked-backup.service" /etc/systemd/system/
install -m 644 "$REPO/deploy/systemd/unlocked-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now unlocked-backup.timer

log "done"
ss -tlnp | grep -E ':(22|22022|80|443|5432) '
