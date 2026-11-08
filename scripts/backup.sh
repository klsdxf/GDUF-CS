#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
target="${1:-backups/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$target"
docker compose exec -T db pg_dump -U gduf -d gduf -Fc > "$target/database.dump"
docker compose exec -T api tar -C /app/storage -czf - media > "$target/media.tar.gz"
cp compose.yaml .env.example "$target/"
sha256sum "$target/database.dump" "$target/media.tar.gz" > "$target/SHA256SUMS"
echo "备份完成：$target；请另存一份到服务器之外。失败由退出码交给 cron/监控告警。"
