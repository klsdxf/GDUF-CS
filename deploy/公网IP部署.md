# 公网 IPv4 HTTPS 入口

沿用现有 `compose.yaml` 和生产 `.env`，不改变数据库密码。入口通过额外 Nginx 容器提供，无需安装系统 Nginx。证书使用 Docker 内的 Certbot；正式证书请求由操作者在服务器终端执行，交互确认邮箱和服务条款。

依据：[Certbot Docker 安装](https://eff-certbot.readthedocs.io/en/stable/install.html#alternative-1-docker)、[Let's Encrypt IP 证书与 webroot 支持](https://letsencrypt.org/2026/03/11/shorter-certs-certbot.html)。IP 证书有效期约6天，必须完成自动续期配置。

前提：基础应用已启动、80/443端口空闲、ECS安全组及服务器防火墙允许公网访问TCP80/443。将以下 IP 换成实际公网 IPv4，`.env` 中 `PUBLIC_ORIGIN` 必须为对应的 `https://IP`。

```bash
git pull --ff-only
bash scripts/ip-https.sh prepare 47.76.165.241
curl --fail http://127.0.0.1/.well-known/acme-challenge/gduf-check
```

从服务器外浏览器打开 `http://IP/.well-known/acme-challenge/gduf-check`，应显示 `gduf-acme-ready`。成功后，在服务器**单独执行**证书申请；按 Certbot 提示输入邮箱并自行决定是否接受条款，不要同时粘贴其他命令：

```bash
bash scripts/ip-https.sh request 47.76.165.241
```

申请成功后：

```bash
bash scripts/ip-https.sh enable 47.76.165.241
bash scripts/ip-https.sh install-timer
curl --fail https://47.76.165.241/api/v1/health
docker compose exec api python -m app.cli init-admin
```

最后一条命令只在首次部署时交互创建唯一管理员，账号密码仅在自己的终端输入。访问 `https://IP/admin/login` 管理赛事。空生产数据库首页显示赛事尚未公布。

日常入口操作必须包含额外的 Compose 文件：

```bash
docker compose -f compose.yaml -f deploy/compose.ip.yaml ps
docker compose -f compose.yaml -f deploy/compose.ip.yaml logs --tail=50 edge
systemctl list-timers gduf-cs-ip-renew.timer --no-pager
journalctl -u gduf-cs-ip-renew.service --no-pager -n 50
```

`bash scripts/ip-https.sh renew` 可手动触发续期检查；只有成功后才重载 Nginx。验证续期可以执行 `docker compose -f compose.yaml -f deploy/compose.ip.yaml run --rm --no-deps certbot renew --cert-name gduf-ip --dry-run`。证书与ACME账号持久化在该Compose项目的 `ip_certificates` 卷中，不上传GitHub；数据库/图片备份脚本仍负责原应用数据。切换机器需要额外受控备份证书卷，或在新机器重新申请证书。
