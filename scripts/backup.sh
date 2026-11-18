#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
target="${1:-backups/$(date -u +%Y%m%dT%H%M%SZ)}"
mode="${2:-online}"
[[ "$mode" == online || "$mode" == consistent ]] || { echo 'backup mode must be online or consistent'; exit 1; }
mkdir -p "$(dirname "$target")"
mkdir "$target"
if [[ "$mode" == consistent ]]; then
  mapfile -t api_instances < <(docker compose ps -q api)
  if (( ${#api_instances[@]} )); then
    trap 'docker start "${api_instances[@]}" >/dev/null' EXIT
    docker compose stop api
  fi
fi
docker compose exec -T db pg_dump -U gduf -d gduf -Fc > "$target/database.dump"
docker compose run --rm -T --no-deps api tar -C /app/storage -czf - media > "$target/media.tar.gz"
docker compose run --rm -T --no-deps api python -m app.verify_restore > "$target/manifest.json"
printf '%s\n' "$mode" > "$target/mode"
docker compose exec -T db psql -U gduf -d gduf -Atc 'SELECT version_num FROM alembic_version' > "$target/revision"
cp compose.yaml .env.example "$target/"
(cd "$target" && sha256sum database.dump media.tar.gz manifest.json mode revision > SHA256SUMS)
if [[ "$mode" == consistent ]] && (( ${#api_instances[@]} )); then
  docker start "${api_instances[@]}" >/dev/null
  trap - EXIT
fi
echo "备份完成：$target"
