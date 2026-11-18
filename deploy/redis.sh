#!/bin/sh
set -eu
case "${REDIS_PASSWORD:-}" in
  ''|*[!A-Za-z0-9_-]*) echo 'REDIS_PASSWORD must contain only URL-safe characters' >&2; exit 1 ;;
esac
umask 077
acl=/tmp/gduf-users.acl
printf '%s\n' 'user default off' > "$acl"
printf 'user gduf on >%s ~* +ping +info +eval +evalsha +script|load +get +set +del +hget +hmget +hset +time +zadd +zcard +zrange +zrem +zremrangebyscore +pexpire +client|setinfo +select\n' "$REDIS_PASSWORD" >> "$acl"
chown redis:redis "$acl"
exec docker-entrypoint.sh redis-server --aclfile "$acl" --appendonly yes \
  --appendfsync everysec --maxmemory 128mb --maxmemory-policy noeviction --save ""
