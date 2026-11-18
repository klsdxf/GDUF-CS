#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
: "${GDUF_BACKUP_ROOT:?Set a protected local backup directory}"
: "${GDUF_BACKUP_REMOTE:?Set an offsite rclone remote and path}"
: "${GDUF_BACKUP_AGE_RECIPIENTS:?Set a file containing public age recipients}"
: "${GDUF_BACKUP_METRICS_DIR:?Set the node exporter textfile directory}"
id="$(date -u +%Y%m%dT%H%M%SZ)"
destination="$GDUF_BACKUP_ROOT/$id"
archive="$GDUF_BACKUP_ROOT/$id.tar.gz.age"
staging="$archive.partial"
trap 'rm -f -- "$staging"' EXIT
# Coordinate database and media on the single API service before uploading.
bash scripts/backup.sh "$destination" consistent
tar -C "$destination" -czf - . | age -R "$GDUF_BACKUP_AGE_RECIPIENTS" -o "$staging"
mv -- "$staging" "$archive"
rclone copyto "$archive" "$GDUF_BACKUP_REMOTE/daily/$id.tar.gz.age"
rclone check --download --include "$id.tar.gz.age" "$GDUF_BACKUP_ROOT" "$GDUF_BACKUP_REMOTE/daily" --one-way
if [[ "$(TZ=Asia/Shanghai date +%u)" == 1 ]]; then
  rclone copyto "$archive" "$GDUF_BACKUP_REMOTE/weekly/$id.tar.gz.age"
fi
if [[ "$(TZ=Asia/Shanghai date +%d)" == 01 ]]; then
  rclone copyto "$archive" "$GDUF_BACKUP_REMOTE/monthly/$id.tar.gz.age"
fi
metric="$GDUF_BACKUP_METRICS_DIR/gduf-backup.prom"
printf 'gduf_backup_last_success_timestamp_seconds %s\n' "$(date +%s)" > "$metric.tmp"
chmod 644 "$metric.tmp"
mv -- "$metric.tmp" "$metric"
