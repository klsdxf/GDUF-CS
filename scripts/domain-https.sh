#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose() { docker compose -f compose.yaml -f deploy/compose.ip.yaml "$@"; }
operation="${1:?用法：bash scripts/domain-https.sh request|enable 完整域名}"
domain="${2:?请提供完整域名，例如 www.gdufcs.fun}"
domain="${domain,,}"
[[ "$domain" =~ ^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$ ]] || { echo '请输入不带协议、端口和路径的完整域名'; exit 1; }
case "$operation" in
  request)
    compose run --rm --no-deps certbot certonly --webroot --webroot-path /var/www/acme --domain "$domain" --cert-name gduf-domain
    ;;
  enable)
    compose exec -T edge sh -c 'test -s /etc/letsencrypt/live/gduf-domain/fullchain.pem && test -s /etc/letsencrypt/live/gduf-domain/privkey.pem'
    umask 077
    mkdir -p storage/domain-backups storage/ip-edge
    backup="storage/domain-backups/$(date -u +%Y%m%dT%H%M%SZ)"
    mkdir "$backup"
    cp -p .env "$backup/environment"
    if [[ -f storage/ip-edge/domain.conf ]]; then cp storage/ip-edge/domain.conf "$backup/domain.conf"; fi
    sed "s/__DOMAIN__/$domain/g" deploy/domain-https.conf > storage/ip-edge/domain.conf.next
    mv storage/ip-edge/domain.conf.next storage/ip-edge/domain.conf
    if ! compose exec -T edge nginx -t; then
      if [[ -f "$backup/domain.conf" ]]; then cp "$backup/domain.conf" storage/ip-edge/domain.conf; else rm -f storage/ip-edge/domain.conf; fi
      echo "配置检查失败，已恢复入口配置；原环境保存在 $backup/environment"; exit 1
    fi
    grep -q '^PUBLIC_ORIGIN=' .env || { echo '缺少 PUBLIC_ORIGIN，请检查生产环境配置'; exit 1; }
    sed -i "s|^PUBLIC_ORIGIN=.*|PUBLIC_ORIGIN=https://$domain|" .env
    export PUBLIC_ORIGIN="https://$domain"
    compose up -d --no-deps --wait api
    compose exec -T web nginx -t
    compose exec -T web nginx -s reload
    compose exec -T edge nginx -s reload
    verified=false
    for attempt in {1..10}; do
      if curl --fail --silent --show-error --max-time 5 --noproxy '*' --connect-to "$domain:443:127.0.0.1:443" "https://$domain/api/v1/health"; then
        printf '\n'; verified=true; break
      fi
      sleep 1
    done
    [[ "$verified" == true ]] || { echo 'HTTPS 健康检查未通过，请检查入口日志和证书；环境备份已保留'; exit 1; }
    echo "域名入口已启用：https://$domain/；请通过新域名重新登录后台。"
    echo "环境配置备份：$backup/environment；数据库密码和业务数据保持原值。"
    ;;
  *) echo '支持 request 或 enable'; exit 1 ;;
esac
