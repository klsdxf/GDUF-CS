#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose() { docker compose -f compose.yaml -f deploy/compose.ip.yaml "$@"; }
operation="${1:-help}"
case "$operation" in
  prepare|request|enable)
    public_ip="${2:?请提供服务器公网 IPv4}"
    [[ "$public_ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || { echo '请输入 IPv4 地址'; exit 1; }
    IFS=. read -r -a octets <<< "$public_ip"
    for octet in "${octets[@]}"; do
      (( 10#$octet <= 255 )) || { echo 'IPv4 地址无效'; exit 1; }
    done
    configured_origin="${PUBLIC_ORIGIN:-$(sed -n 's/^PUBLIC_ORIGIN=//p' .env)}"
    [[ "$configured_origin" == "https://$public_ip" ]] || { echo 'PUBLIC_ORIGIN 必须与 https://公网IP 一致；保留数据库密码，仅修改访问地址'; exit 1; }
    ;;
esac
case "$operation" in
  prepare)
    mkdir -p storage/ip-edge
    if [[ -f storage/ip-edge/default.conf ]]; then
      echo '入口配置已存在，保留原配置'
    else
      sed "s/__PUBLIC_IP__/$public_ip/g" deploy/ip-bootstrap.conf > storage/ip-edge/default.conf
    fi
    compose up -d --no-deps edge
    compose exec -T edge sh -c 'mkdir -p /var/www/acme/.well-known/acme-challenge; printf "gduf-acme-ready\n" > /var/www/acme/.well-known/acme-challenge/gduf-check'
    compose exec -T edge nginx -t
    echo "证书验证入口已准备：http://$public_ip/.well-known/acme-challenge/gduf-check"
    ;;
  request)
    compose run --rm --no-deps certbot certonly --webroot --webroot-path /var/www/acme --preferred-profile shortlived --ip-address "$public_ip" --cert-name gduf-ip
    ;;
  enable)
    compose exec -T edge sh -c 'test -s /etc/letsencrypt/live/gduf-ip/fullchain.pem && test -s /etc/letsencrypt/live/gduf-ip/privkey.pem'
    cp storage/ip-edge/default.conf storage/ip-edge/default.conf.bak
    sed "s/__PUBLIC_IP__/$public_ip/g" deploy/ip-https.conf > storage/ip-edge/default.conf.next
    mv storage/ip-edge/default.conf.next storage/ip-edge/default.conf
    if ! compose exec -T edge nginx -t; then
      cp storage/ip-edge/default.conf.bak storage/ip-edge/default.conf
      echo '配置检查失败，已恢复原配置'; exit 1
    fi
    compose exec -T edge nginx -s reload
    echo "HTTPS 已启用：https://$public_ip/；下一步执行 install-timer 配置自动续期"
    ;;
  renew)
    compose run --rm --no-deps -T certbot renew --non-interactive
    compose exec -T edge nginx -t
    compose exec -T edge nginx -s reload
    ;;
  install-timer)
    [[ "$EUID" == 0 ]] || { echo '需要 root 权限安装 systemd 定时任务'; exit 1; }
    cat > /etc/systemd/system/gduf-cs-ip-renew.service <<EOF
[Unit]
Description=Renew GDUF CS public IP certificate
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=oneshot
ExecStart=/usr/bin/bash "$PWD/scripts/ip-https.sh" renew
EOF
    cat > /etc/systemd/system/gduf-cs-ip-renew.timer <<'EOF'
[Unit]
Description=Renew GDUF CS public IP certificate twice daily
[Timer]
OnCalendar=*-*-* 03,15:15:00
RandomizedDelaySec=900
Persistent=true
[Install]
WantedBy=timers.target
EOF
    systemctl daemon-reload
    systemctl enable --now gduf-cs-ip-renew.timer
    systemctl list-timers gduf-cs-ip-renew.timer --no-pager
    ;;
  *)
    echo '用法：bash scripts/ip-https.sh prepare|request|enable 公网IPv4'
    echo '      bash scripts/ip-https.sh install-timer|renew'
    exit 1
    ;;
esac
