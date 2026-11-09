#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose() { docker compose -f compose.yaml -f deploy/compose.ip.yaml "$@"; }
operation="${1:?用法：bash scripts/domain-https.sh request|enable 完整域名 [跳转域名...]}"
domain="${2:?请提供完整域名，例如 www.gdufcs.fun}"
domain="${domain,,}"
[[ "$domain" =~ ^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$ ]] || { echo '请输入不带协议、端口和路径的完整域名'; exit 1; }
redirect_hosts="${*:3}"
domain_args=(--domain "$domain")
for host in $redirect_hosts; do
  [[ "$host" =~ ^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$ && "$host" != "$domain" ]] || { echo '跳转域名无效或与规范域名相同'; exit 1; }
  domain_args+=(--domain "$host")
done
case "$operation" in
  request)
    compose run --rm --no-deps certbot certonly --webroot --webroot-path /var/www/acme "${domain_args[@]}" --expand --cert-name gduf-domain
    ;;
  enable)
    compose exec -T edge sh -c 'test -s /etc/letsencrypt/live/gduf-domain/fullchain.pem && test -s /etc/letsencrypt/live/gduf-domain/privkey.pem'
    umask 077
    mkdir -p storage/domain-backups storage/ip-edge
    backup="storage/domain-backups/$(date -u +%Y%m%dT%H%M%SZ)"
    mkdir "$backup"
    cp -p .env "$backup/environment"
    if [[ -f storage/ip-edge/domain.conf ]]; then cp storage/ip-edge/domain.conf "$backup/domain.conf"; fi
    # Both hosts must already serve the webroot challenge before request/enable.
    redirect_server=""
    if [[ -n "$redirect_hosts" ]]; then
      redirect_server="server { listen 443 ssl; http2 on; server_name $redirect_hosts; ssl_certificate /etc/letsencrypt/live/gduf-domain/fullchain.pem; ssl_certificate_key /etc/letsencrypt/live/gduf-domain/privkey.pem; ssl_protocols TLSv1.2 TLSv1.3; include /etc/nginx/snippets/security-headers.conf; add_header Strict-Transport-Security \"max-age=86400\" always; return 301 https://$domain\$request_uri; }"
    fi
    sed -e "s/__DOMAIN__/$domain/g" -e "s/__REDIRECT_HOSTS__/$redirect_hosts/g" -e "s|__REDIRECT_SERVER__|$redirect_server|g" deploy/domain-https.conf > storage/ip-edge/domain.conf.next
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
