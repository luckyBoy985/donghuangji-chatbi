# 多用户 ChatBI 本地 Docker 部署

## 资源要求

- Windows + Docker Desktop，启用 NVIDIA GPU 容器支持。
- 至少 25 GB 可用磁盘用于 CUDA 镜像层、模型与容器数据。
- 本机 GPU 用于 API 问答和 Worker 文档向量化；Worker 固定并发为 1，避免重复加载模型。
- API 与 Worker 以 UID/GID `10001` 非 root 运行；Linux 宿主机需确保运行目录可写：

```bash
sudo chown -R 10001:10001 data/runtime
```
- 模型目录通过 `.env` 中的 `MODEL_ROOT` 指定，默认是项目上级目录的 `BAAI`。

## 对外端口

默认只暴露 nginx：

```text
http://127.0.0.1:8080
```

PostgreSQL、Redis、MinIO、API、Worker 均只在 Docker 私有网络内。

## 首次启动

```powershell
Copy-Item .env.production.example .env
```

必须替换：

- `POSTGRES_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `SECRET_KEY`
- `BOOTSTRAP_ADMIN_TOKEN`
- `MCP_ACCESS_TOKEN`
- `DEEPSEEK_API_KEY`

如果局域网使用非 `127.0.0.1:8080` 地址，保持 `ALLOWED_ORIGIN` 为实际浏览器地址，或依靠同 Host 校验使用服务器局域网 IP。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
docker compose ps
```

打开网页后，使用 `BOOTSTRAP_ADMIN_TOKEN` 创建首位平台管理员。创建成功后 setup 入口永久关闭。

用户忘记密码时，由平台管理员进入“用户”页生成一次性临时密码。临时密码只显示一次，用户登录后必须先修改密码。

API 启动时会自动执行：

- Alembic 升级到最新版本。
- 初始化私有 MinIO bucket。
- 把仓库内演示语料幂等同步到 `data_documents` 和 `data_chunks`；生产环境请先导入自有数据。
- 升级到安全加固迁移，增加强制改密和登录失败追踪表。

## 数据管理

首位管理员创建后进入“管理 → 数据管理”：

- 上传 PDF、DOCX、XLSX/XLSM、CSV/TSV、Markdown、TXT，原始文件写 MinIO。
- 对四站官网执行增量重抓；抓取为空时不删除旧资料，同范围抓取量不足已有 80% 时跳过下架判定。
- 查看后台任务、错误原因、文档原文和分块数量。
- 归档/恢复文档或手动重建索引。

上传和重抓由 Celery Worker 解析、切块、调用 BGE-M3 并原子生成：

```text
data/runtime/index/platform_index.pkl
data/runtime/index/platform_index.manifest.json
```

API 会在下一次检索时检测索引版本并自动重载；基线 `local_index.pkl` 不会被覆盖。健康接口会比较 manifest 的 SHA-256、数据库指纹、模型版本和分块数量。

## 资源限制与维护

- `QA_MAX_CONCURRENCY` 控制 API 内的 GPU 重活并发，默认 2。
- `QA_DAILY_LIMIT_PER_USER`、`REPORT_DAILY_LIMIT_PER_USER` 和 `ADMIN_DATA_DAILY_LIMIT` 控制每日配额。
- Celery 软超时默认 30 分钟，硬超时 31 分钟。
- Celery Beat 每小时执行审计清理、登录失败记录清理和中断任务恢复。
- 单个官网抓取请求默认间隔 1 秒，`CRAWL_DELAY_SECONDS` 可调整。

## 旧数据迁移

先把旧 SQLite 与同名 `-wal`、`-shm` 文件复制到 `data/legacy/chatbi-v1.db*`，并将 SQLite 数据合并为单文件。迁移：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/migrate.ps1 -Owner admin
```

迁移保留 conversation/message/citation/report ID，把会话归属指定管理员。相同源文件重复执行会返回 `skipped=true`。

## 验收

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-docker.ps1
powershell -ExecutionPolicy Bypass -File scripts/test.ps1
```

`scripts/start.ps1` 会先运行配置检查，拒绝占位密钥、过短密钥和被 Git 跟踪的 `.env`。

验证内容包括依赖健康、Worker 在线、数据库和 MinIO 持久化、认证隔离、共享只读、个人副本和数据任务路由。完整上传/抓取联调会真实调用 GPU 模型，首次执行需要等待模型加载。

## 重启与恢复

```powershell
docker compose restart
docker compose ps
```

命名卷：

- `donghuangji-chatbi_postgres-data`
- `donghuangji-chatbi_redis-data`
- `donghuangji-chatbi_minio-data`

除 PostgreSQL 卷外，还需备份：

- MinIO bucket `chatbi` 中的原始上传文件。
- 宿主目录 `data/runtime/index/platform_index.pkl`。
- 与索引同批生成的 `data/runtime/index/platform_index.manifest.json`。

如果平台索引丢失，可从 PostgreSQL 活动分块重新生成：

```powershell
docker compose exec api python -c "from backend.app.core.database import SessionLocal; from backend.app.services.ingestion.service import rebuild_index; db=SessionLocal(); print(rebuild_index(db)); db.close()"
```

该命令会在 API 容器中加载 BGE-M3。执行前建议停止 Worker，避免两个进程同时进行大模型推理。

常规升级不要执行 `docker compose down -v`，该参数会删除持久化业务数据。

PostgreSQL 备份：

```powershell
docker compose exec -T postgres pg_dump -U chatbi chatbi > backups\chatbi.sql
```

恢复前先停止 API 与 Worker，再使用 `psql` 导入备份。

## 日志

```powershell
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f nginx
```

## 公网部署前

- 配置域名和 HTTPS，并设置 `SESSION_COOKIE_SECURE=true`。
- 限制 nginx 来源 IP 或增加统一认证网关。
- 将 `BOOTSTRAP_ADMIN_TOKEN` 从运行环境移除。
- 设置备份保留、监控、告警和日志轮转。
- 轮换所有写入过终端或对话记录的密钥。
- 立即轮换曾在聊天或日志工具中出现过的 DeepSeek Key。
