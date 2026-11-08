# 广金主场 · GDUF CS2

广东金融学院学生社团 CS2 赛事展示与单管理员管理平台。Vue 3 + TypeScript + Element Plus / FastAPI + SQLAlchemy + Alembic / PostgreSQL / Nginx。开发依据见 [开发文档](开发文档/00_开发文档索引与决策记录.md)。

## 本地运行

Python 3.12、Node 22+。在仓库根目录执行：

```powershell
python -m venv .venv
./.venv/Scripts/python -m pip install -r backend/requirements.lock
cd backend
../.venv/Scripts/python -m alembic upgrade head
../.venv/Scripts/python -m app.cli init-admin
../.venv/Scripts/python -m uvicorn app.main:app --reload
```

另开终端：

```powershell
cd frontend
npm ci
npm run dev
```

访问 `http://localhost:5173`，后台为 `/admin/login`；OpenAPI 为 `http://127.0.0.1:8000/docs`。本地默认 SQLite 仅用于开发，生产通过 `DATABASE_URL` 使用 PostgreSQL。没有默认密码、真实选手资料或自动发布的示例赛事。

## 管理操作顺序

1. 创建赛事，填写稳定路径、赛季、组织方、实际地图池及正式规则，保存并发布。
2. 手工录入整队，或下载 v1 Excel 模板；填写“队伍”“成员”两表，SteamID64 按原始文本保存。选择赛事及新增/更新，上传仅预览；解决全部错误后确认整批导入。
3. 选择三种赛制之一，配置 BO、分组、晋级、季军赛和双败重置规则；按顺序选择种子，保存后生成草稿。预览并安排时间，正式发布。发布后禁止重新生成覆盖。
4. 比赛进行时维护状态，逐地图保存成绩草稿，再正式确认；后端计算胜者并推进。小组全部结束后处理同分并确认晋级。修正先填写原因、预览下游影响，再提交。
5. 发布公告，手工维护 B站直播状态及回放，比赛结束后归档。游客可以继续使用稳定历史链接。

公开 JSON 通过白名单输出，不含联系方式、Steam ID、导入差异或审计数据。管理员 Cookie 为 HttpOnly；写请求需同源与 CSRF 令牌。

## Ubuntu 24.04 部署

1. 安装 Docker Engine 与 Compose，复制 `.env.example` 为 `.env`，设置随机 URL 安全数据库密码和实际 HTTPS `PUBLIC_ORIGIN`。`.env` 不入库。
2. `docker compose up -d --build`。数据库无宿主机端口；迁移服务成功后 API 启动。
3. `docker compose exec api python -m app.cli init-admin` 交互创建唯一账号。忘记密码用 `reset-password`，会使旧会话失效。
4. 使用主机 Nginx/Caddy 将实际域名的 HTTPS 反代到 `127.0.0.1:8080`；证书由实际域名配置。生产 Cookie 为 Secure，需要 HTTPS。
5. 检查 `/api/v1/health`、管理登录和只读页面。没有服务器和域名配置时，这套配置不代表已经公网部署。

```nginx
server {
  listen 443 ssl;
  server_name cs.example.edu.cn;
  ssl_certificate /etc/letsencrypt/live/cs.example.edu.cn/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/cs.example.edu.cn/privkey.pem;
  client_max_body_size 5m;
  location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
  }
}
```

## 备份、恢复与升级

每日 `bash scripts/backup.sh`，失败退出码接入实际监控；保留最近7份及关键节点备份，至少一份异地保存。包含数据库、图片和非秘密配置；实际 `.env` 密钥独立受控保存。恢复只向独立空库执行 `bash scripts/restore.sh backups/时间 EMPTY_DATABASE_ONLY`，对照计数与图片后再切换流量。脚本不会清空现有数据库。

升级前备份，`docker compose build` 后让迁移单次运行成功，再更新 API 和静态前端。保留旧镜像；不兼容迁移不能只回滚镜像，需使用经验证的数据库恢复流程。

## 开发与验收状态

文档阶段 1～7 为功能开发，阶段 8 统一审查与测试。具体执行结果、环境限制和待处理事项以 `验收报告.md` 为准，不把源码存在等同于验收通过。首页设计对照组件只在开发模式启用，不作为正式赛事数据。
