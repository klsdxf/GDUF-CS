#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source_dir="${1:?用法：restore.sh 备份目录 EMPTY_DATABASE_ONLY}"
[[ "${2:-}" == "EMPTY_DATABASE_ONLY" ]] || { echo '仅允许恢复到空数据库，请传入 EMPTY_DATABASE_ONLY'; exit 1; }
(cd "$source_dir" && sha256sum -c SHA256SUMS)
count=$(docker compose exec -T db psql -U gduf -d gduf -Atc "select count(*) from information_schema.tables where table_schema='public'")
[[ "$count" == "0" ]] || { echo '目标数据库不是空库，停止恢复'; exit 1; }
docker compose run --rm -T --no-deps api python -c \
  'from pathlib import Path; assert not any(Path("/app/storage/media").iterdir()), "Target media volume must be empty"'
docker compose exec -T db pg_restore -U gduf -d gduf --exit-on-error < "$source_dir/database.dump"
docker compose run --rm -T --no-deps api tar -C /app/storage -xzf - < "$source_dir/media.tar.gz"
if [[ -f "$source_dir/manifest.json" ]]; then
  docker compose run --rm -T --no-deps api python -m app.verify_restore --expect < "$source_dir/manifest.json"
else
  docker compose run --rm -T --no-deps api python -m app.verify_restore
fi
