# 🔌 API 与架构开发指南 (API & Architecture Docs)

本项目 `douyin-stream` 在设计之初，就充分考虑了模块化与二次开发的可能。如果你希望将本项目接入你自己的 SaaS 服务、Web 后端（如 FastAPI / Django）或替换存储引擎，这份文档将为你提供关键的架构信息。

---

## 1. 核心模块与入口函数

### 1.1 统一配置加载 (`core/config.py`)
```python
from media_tools.core.config import AppConfig, get_app_config, get_runtime_setting_int

# 获取应用配置（从 SystemSettings 表读取运行时配置）
config = get_app_config()
concurrency = config.concurrency  # 实际并发 = Qwen 账号数
auto_transcribe = config.auto_transcribe

# 读取单个设置值
val = get_runtime_setting_int("concurrency", 10)
```

### 1.2 转写流水线 (`pipeline/orchestrator.py`, `pipeline/worker.py`)
```python
from media_tools.pipeline.orchestrator import create_orchestrator
from media_tools.pipeline.worker import run_local_transcribe, run_pipeline_for_user, run_batch_pipeline
```

### 1.3 额度领取 (`services/qwen_status.py`)
```python
from media_tools.services.qwen_status import claim_qwen_quota, get_qwen_account_status

# 手动领取额度（force=True，直接调 API）
result = await claim_qwen_quota()

# 查询账号状态和剩余额度
status = await get_qwen_account_status()
```

---

## 2. 数据库设计 (SQLite: `data/media_tools.db`)

项目运行时使用 `data/media_tools.db`（路径可通过 `config/config.yaml` 配置）。数据库使用 WAL 模式，支持并发读写。

### 2.1 核心业务表

| 表名 | 用途 |
| :--- | :--- |
| `media_assets` | 素材表：存储视频/音频文件的元数据和转写状态 |
| `creators` | 创作者表：存储博主信息及下载/转写统计 |
| `task_queue` | 任务队列：存储下载、转写等后台任务的执行状态 |

### 2.2 配置与辅助表

| 表名 | 用途 |
| :--- | :--- |
| `SystemSettings` | 系统设置：运行时配置（KV 存储），含 `concurrency`（内部参考值）、`auto_transcribe`、`auto_delete`、`api_key`、`export_format` |
| `Accounts_Pool` | 统一账号池：管理所有平台（抖音/B站/Qwen）的 Cookie 和账号状态。Qwen 活跃账号数决定实际转写并发数 |
| `transcribe_runs` | 转写运行记录：每个视频在某个 Qwen 账号上的完整转写尝试（含断点续传） |
| `scheduled_tasks` | 定时任务：自动领取 Qwen 额度等定时任务配置 |
| `auth_credentials` | 认证凭据：Qwen 兼容回退层（逐步废弃，新代码使用 `Accounts_Pool`） |
| `assets_fts` | 全文搜索索引：素材内容搜索 |
| `video_metadata` | 视频元数据：存放视频详细信息 |
| `user_info_web` | 用户信息：存放创作者公开信息 |

### 2.3 状态字段说明

- `media_assets.download_status`: `pending` | `downloading` | `completed` | `failed`
- `media_assets.transcript_status`: `pending` | `transcribing` | `completed` | `failed`
- `task_queue.status`: `PENDING` | `RUNNING` | `COMPLETED` | `FAILED` | `PARTIAL_FAILED`
- `transcribe_runs.stage`: `queued` | `uploaded` | `transcribing` | `exporting` | `downloading` | `saved` | `failed`

---

## 3. 架构演进建议

如果你准备将本项目部署到生产级服务器或开源社区的高可用场景，建议进行以下改造：

### 3.1 架构演进方向

| 方向 | 说明 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- |
| **转写并发自动跟随账号池** | `effective_concurrency = n_accounts`，无需手动设置 | P0 | ✅ 已完成 |
| **额度领取时区一致性** | `today_key()` 使用本地时间，与 CronTrigger 一致 | P0 | ✅ 已完成 |
| **手动领取绕过缓存检查** | 手动点击直接调 Qwen API（force=True），不受本地缓存限制 | P0 | ✅ 已完成 |
| **API 路由尾部斜杠统一** | 添加 `redirect_slashes=False` 消除 307 重定向 | P0 | ✅ 已完成 |
| **替换 SQLite 为 MySQL/PostgreSQL** | 当前 SQLite 已满足单机需求。如需多实例部署可考虑迁移 | P2 | 待评估 |
| **剥离 Web 看板为独立服务** | 前端已独立为 SPA + FastAPI 后端，当前架构合理 | P3 | 不需要 |
| **加入 Celery 任务队列** | 当前使用 asyncio + APScheduler 已足够，暂不需要引入额外依赖 | P3 | 不需要 |

### 3.2 并发控制体系

系统采用三层信号量控制并发：

| 层级 | 信号量 | 初始值 | 作用 |
| :--- | :--- | :--- | :--- |
| L1 | `_effective_concurrency` | Qwen 活跃账号数 | 同时处理的视频数 |
| L2 | `upload_gate` | 活跃账号数 | 同时上传到 Qwen 的数量 |
| L3 | `export_gate` | min(2×账号数, 8) | 同时从 Qwen 导出的数量 |