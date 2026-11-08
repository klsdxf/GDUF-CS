#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source_dir="${1:?用法：restore.sh 备份目录 EMPTY_DATABASE_ONLY}"
[[ "${2:-}" == "EMPTY_DATABASE_ONLY" ]] || { echo '仅允许恢复到空数据库，请传入 EMPTY_DATABASE_ONLY'; exit 1; }
sha256sum -c "$source_dir/SHA256SUMS"
count=$(docker compose exec -T db psql -U gduf -d gduf -Atc "select count(*) from information_schema.tables where table_schema='public'")
[[ "$count" == "0" ]] || { echo '目标数据库不是空库，停止恢复'; exit 1; }
docker compose exec -T db pg_restore -U gduf -d gduf --exit-on-error < "$source_dir/database.dump"
docker compose run --rm -T --no-deps api tar -C /app/storage -xzf - < "$source_dir/media.tar.gz"
docker compose run --rm --no-deps api python -m app.verify_restore
