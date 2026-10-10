#!/usr/bin/env bash
set -euo pipefail

# Run from the repository root on the GitHub-hosted Linux runner.
for name in DEPLOY_HOST DEPLOY_PORT DEPLOY_USER DEPLOY_PATH DEPLOY_PYTHON DEPLOY_SSH_KEY DEPLOY_KNOWN_HOSTS; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing configuration: $name" >&2
    exit 1
  fi
done

# These values enter SSH configuration and remote shell commands.
[[ "$DEPLOY_HOST" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]]
[[ "$DEPLOY_USER" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_-]*$ ]]
[[ "$DEPLOY_PORT" =~ ^[0-9]{1,5}$ ]]
(( 10#$DEPLOY_PORT >= 1 && 10#$DEPLOY_PORT <= 65535 ))
for name in DEPLOY_PATH DEPLOY_PYTHON; do
  value="${!name}"
  if [[ ! "$value" =~ ^/[a-zA-Z0-9_./-]+$ || "$value" == *'/../'* || "$value" == */.. ]]; then
    echo "$name must be an absolute path without spaces or shell metacharacters." >&2
    exit 1
  fi
done
test -f frontend/dist/index.html

umask 077
mkdir -p "$HOME/.ssh"
key_file="$HOME/.ssh/portfel_deploy"
hosts_file="$HOME/.ssh/portfel_known_hosts"
config_file="$HOME/.ssh/portfel_config"
trap 'rm -f "$key_file" "$hosts_file" "$config_file"' EXIT
printf '%s\n' "$DEPLOY_SSH_KEY" > "$key_file"
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$hosts_file"
cat > "$config_file" <<EOF
Host portfel-deploy
  HostName $DEPLOY_HOST
  Port $DEPLOY_PORT
  User $DEPLOY_USER
  IdentityFile $key_file
  UserKnownHostsFile $hosts_file
  StrictHostKeyChecking yes
  IdentitiesOnly yes
  BatchMode yes
  ConnectTimeout 15
EOF

# Refuse to deploy to an unconfigured application or a system Python by mistake.
ssh -F "$config_file" portfel-deploy bash -s -- "$DEPLOY_PATH" "$DEPLOY_PYTHON" <<'REMOTE'
set -euo pipefail
root="$1"
python="$2"
test -f "$root/backend/passenger_wsgi.py"
test -x "$python"
command -v rsync >/dev/null
"$python" -c 'import sys; assert sys.prefix != sys.base_prefix, "DEPLOY_PYTHON must be a virtualenv Python"'
mkdir -p "$root/backend/frontend_dist" "$root/data" "$root/backend/tmp"
REMOTE

# No --delete: preserve cPanel configuration and all server-owned files.
rsync -az -e "ssh -F $config_file" \
  --exclude='passenger_wsgi.py' --exclude='.htaccess' --exclude='.git*' \
  --exclude='.venv*' --exclude='__pycache__/' --exclude='.pytest_cache/' \
  --exclude='tests/' --exclude='node_modules/' --exclude='tmp/' \
  --exclude='frontend_dist/' --exclude='.env*' --exclude='*.db*' --exclude='*.sqlite*' \
  backend/ "portfel-deploy:$DEPLOY_PATH/backend/"
rsync -az -e "ssh -F $config_file" \
  frontend/dist/ "portfel-deploy:$DEPLOY_PATH/backend/frontend_dist/"
rsync -az -e "ssh -F $config_file" \
  data/nasdaq_stocks.json data/nyse_stocks.json "portfel-deploy:$DEPLOY_PATH/data/"

ssh -F "$config_file" portfel-deploy bash -s -- "$DEPLOY_PATH" "$DEPLOY_PYTHON" <<'REMOTE'
set -euo pipefail
root="$1"
python="$2"
cd "$root/backend"
"$python" -m pip install -r requirements.txt
touch tmp/restart.txt
REMOTE
