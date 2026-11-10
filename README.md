# 广金主场 · GDUF CS2

广东金融学院学生社团 CS2 赛事展示与单管理员管理平台。Vue 3 + TypeScript + Element Plus / FastAPI + SQLAlchemy + Alembic / PostgreSQL / Nginx。开发依据见 [开发文档](开发文档/00_开发文档索引与决策记录.md)。

当前线上环境、管理员交接、更新发布、证书续期和备份恢复见 [项目交接文档](项目交接文档.md)。正式入口为 <https://www.gdufcs.fun/>；实际服务器使用 Alibaba Cloud Linux 3，下文 Ubuntu 部署为通用方案。

## 2026-11-10 示例数据后端化

**生产发布补充：两项更新及媒体路由修复已于 2026-11-10 上线，当前运行源码为 `6a31f27`。** 生产数据库为 004，四队与新队标已发布，首次悬停已通过公网浏览器验证。实际批次、备份与回退点见 [阿里云发布记录](deploy/两项更新阿里云发布记录_2026-11-10.md)。本节后续涉及“未部署”的叙述为最初源码交付阶段的范围，不覆盖此条发布补充。

当前发布构建默认读取后端 API。后台新增“测试数据初始化”，先预览再确认提交 `public-test / v1` 数据包：三届赛事目录、秋季赛四队和名单、现有赛程、三条公告、合作与奖品及独立测试排名。冠军为 **Poppin'Party**，秋季赛继续显示进行中。前台取消示例标注，后台保留测试身份；最终排名沿用 V6 样式与动效，15 件外设、20 枚徽章从分配记录计算。

升级先备份，执行 `alembic upgrade head` 至 004，并更新后端；管理员在后台预览、提交数据，再以 API 模式重建前端。相同数据包重复提交返回原批次，不覆盖人工修改；同路径赛事或同名品牌冲突会阻止初始化。已有资料不要清库重装，应先核对冲突。

测试排名对局与正常赛程独立，编辑后需预览、校验、发布才能更新公开版本；公告等资料按原后台流程保存。数据库结构迁移不会自动导入测试内容，也不会创建管理员或更改现有密码。此轮交付不代表生产服务器已经升级。

详细方案见 [15 号技术文档](开发文档/15_示例数据后端化与四队测试排名技术开发方案_2026-11-10.md)，实现与验证见 [16 号交付记录](开发文档/16_示例数据后端化开发交付与验证_2026-11-10.md)。下文 11 月 9 日交付描述属于历史阶段；默认模式及初始化方式以本节和“前台数据模式”为准。

## 2026-11-09 前端重设计

现行设计已切换为 GDUF CS 深色赛事门户，包含最后确认的右下品牌微调及中文说明移除。新版 Vue 前台已按冻结稿迁移，保留后台与原业务接口。默认交付为明确标识的演示模式；真实数据模式通过构建配置选择。验收与必要差异见 [重设计交付报告](开发文档/08_前端重设计交付与验收.md)。

- [重设计开发方案](开发文档/07_前端重设计开发方案_2026-11-09.md)：与示例一模一样、后端全部保留、先实现功能，最后一轮审查测试。
- [已确认可交互页面](开发文档/前端设计基准/GDUFCS_2026重设计_已确认/index.html)及[基准说明](开发文档/前端设计基准/GDUFCS_2026重设计_已确认/README.md)。
- [示例赛事数据](开发文档/前端设计基准/GDUFCS_2026重设计_已确认/示例赛事数据.json)：先随首版保存／推送，后续按实际内容修改；演示模式明确标识，不自动写入生产数据库。

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

每日 `bash scripts/backup.sh`，失败退出码接入实际监控；保留最近7份及关键节点备份，至少一份异地保存。包含数据库、图片和非秘密配置；实际 `.env` 密钥独立受控保存。恢复时先在独立部署目录构建镜像，仅启动 `docker compose up -d db`（不要先执行迁移）；只向独立空库执行 `bash scripts/restore.sh backups/时间 EMPTY_DATABASE_ONLY`，对照计数与图片后再 `docker compose up -d` 并切换流量。脚本不会清空现有数据库。

升级前备份，`docker compose build` 后让迁移单次运行成功，再更新 API 和静态前端。保留旧镜像；不兼容迁移不能只回滚镜像，需使用经验证的数据库恢复流程。

## 开发与验收状态

文档阶段 1～7 为功能开发，阶段 8 统一审查与测试。具体执行结果、环境限制和待处理事项以 `验收报告.md` 为准，不把源码存在等同于验收通过。旧版首页设计对照组件只在开发模式启用；本轮新设计与演示数据交付安排见重设计方案，不把示例称作真实赛事数据。

## 前台数据模式

`frontend/.env.local` 可设置 `VITE_PUBLIC_DATA_MODE=demo` 或 `api`，修改后重启开发服务／重新构建。未配置时采用 `api`；不存在“数据库为空就自动回退示例”的行为。

- `demo`：显式启用的历史冻结设计参考，仅用于开发与原视觉回归，不用于本轮公开交付。管理后台始终连接真实后端。
- `api`：默认发布模式，读取公开接口。业务数据通过后台录入或显式初始化；错误与空数据不回退演示。API 构建不包含冻结示例数据模块。

Docker Compose 从根目录环境配置读取同名构建参数；切换模式后须重建 `web`。本轮上传源码不包含生产部署或数据库变更。

前端验收：`cd frontend; npm run test:e2e`。测试自动启动两种模式的本机服务及只读冻结稿服务。Windows 使用本机 Edge；Linux 先执行 `npx playwright install --with-deps chromium`。真实后台闭环单独启用 `E2E=1` 并准备独立验收数据库，见交付报告。

## 2026-11-09 审计修复

两种前台数据模式的可读性、直播状态、队伍链接、错误页和静态资源已按审计方案修正，并补充资源页公开性校验及 Nginx 构建配置。详见 [实施与验证记录](开发文档/10_审计修复实施与验证_2026-11-09.md)。本地验证不代表生产部署验收；DNS/证书与公网响应仍需按记录复测。


## 最终排名与赞助展示 V6

新增一级入口 `/results` 与历史页 `/results/:slug`，导航顺序为首页、赛事、赛程、战队、最终排名、公告。沿用 demo/API 构建模式；赛后演示数据独立保存，API 模式只读取有效的正式发布快照。

后台选择赛事 → **最终排名与奖励**：保存最终阶段 → 生成候选名次 → 核对队伍资料版本及领取人数 → 维护品牌、本届合作、奖品 → 分配奖励 → 内部预览 → 校验 → 填写原因并发布。无季军赛保留并列 3–4；双败按实际 final/reset 决定冠军。重新计算或替换名次会清空工作稿奖励分配，应在分配前完成名次维护。正式赛果修正会在同一事务中使受影响的公开结果失效，重发后恢复。

增量迁移为 `003`；升级前备份，随后执行 `alembic upgrade head` 并重建前端。此次源码交付不执行生产迁移。详细实施与验证证据见 [最终排名开发交付记录](开发文档/13_最终排名V6开发交付与验证.md)。独立真实 API 浏览器验收：`cd frontend` 后执行 `npx playwright test --config playwright.results-live.config.ts`；该命令自动创建合成验收库并启动专用本机服务，不使用现有数据库。
