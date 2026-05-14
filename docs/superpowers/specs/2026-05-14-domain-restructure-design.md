# media-tools 领域重组设计 (Domain Restructure)

## 背景

media-tools 项目目前约 3 万行 Python 代码，模块按"技术层次"组织（`api/`、`services/`、`workers/`、`pipeline/`、`repositories/`）。随着功能迭代，同一业务逻辑分散在多个层次中，导致：

- 改一个功能要同时动 `services/`、`workers/`、`pipeline/` 等多个目录
- `services/` 成为大杂烩，混杂了业务逻辑、任务管理、基础设施工具、健康监控
- `pipeline/` 与 `transcribe/` 高度耦合但物理分离
- `workers/` 与 `services/` 存在循环依赖
- 配置文件、日志散落在多个层级

本次重构目标：按"能力（Capability）"重新组织模块，消除场景驱动的代码重复，建立清晰的依赖方向和功能扩展路径。

## 目标

1. **单一能力单一模块**：每个核心能力只存在于一个模块，不被场景重复引用
2. **同层不互相依赖**：能力模块之间通过调度层协调，不直接耦合
3. **上层调下层**：依赖方向统一为 `api → scheduler → 业务 → platform/store`
4. **配置/日志统一**：所有配置集中到 `config/`，所有日志集中到 `logs/`
5. **测试镜像**：测试目录结构与源码一致

## 架构设计

### 核心能力划分

| 能力 | 职责 | 原则 |
|------|------|------|
| **platform** | 和外部平台 API 通信（抖音、B站） | 只调外部，不依赖内部业务 |
| **download** | 给定 URL/ID，拿到视频文件 | 用 platform，存结果到 assets |
| **transcribe** | 给定视频文件，拿到文本 | 用外部转写服务，更新 assets |
| **assets** | 管理 media_assets、文件、GC | 只操作数据和文件 |
| **scheduler** | 任务队列、worker 分发、状态、重试 | 协调 download/transcribe/assets |
| **api** | HTTP 接口、WebSocket | 只路由，不碰业务逻辑 |
| **store** | 数据库、模型定义 | 最底层，不依赖业务 |
| **core** | 配置、日志、异常、事件 | 最底层，不依赖业务 |

### 依赖规则

```
api/
  → scheduler/
  → download/  (只读查询)
  → transcribe/ (只读查询)
  → assets/    (只读查询)

scheduler/
  → download/
  → transcribe/
  → assets/
  → platform/  (平台相关任务)

download/
  → platform/
  → assets/
  → store/

transcribe/
  → assets/
  → store/
  → platform/  (如需要)

assets/
  → store/

platform/
  → core/      (配置、日志)
  → (外部 API)

store/, core/
  → (不依赖任何业务模块)
```

**红线**：`download/` 不直接调 `transcribe/`，`transcribe/` 不直接调 `download/`。两者由 `scheduler/` 按流程串联。

### 顶层结构

```
src/media_tools/
├── __init__.py
│
├── platform/              # 平台交互
│   ├── __init__.py
│   ├── base.py            # PlatformAdapter 抽象接口
│   ├── douyin.py          # 抖音 API 封装（原 douyin/ 合并）
│   └── bilibili.py        # B站 API 封装（原 bilibili/ 合并）
│
├── download/              # 下载能力
│   ├── __init__.py
│   ├── service.py         # 下载调度（原 pipeline/download_router.py 调度逻辑）
│   └── worker.py          # 下载执行（DownloadWorker）
│
├── transcribe/            # 转写能力
│   ├── __init__.py
│   ├── service.py         # 转写调度（原 pipeline/orchestrator.py 核心）
│   ├── worker.py          # 转写执行（CreatorTranscribeWorker, LocalTranscribeWorker）
│   ├── flow.py            # 转写流程（原 transcribe/flow.py）
│   ├── accounts.py        # 账号池（原 services/account_pool_service.py + transcribe/accounts.py）
│   ├── runs.py            # 转写运行记录（原 services/transcribe_run_service.py）
│   ├── quota.py           # 原 transcribe/quota.py
│   ├── error_types.py     # 原 pipeline/error_types.py
│   ├── models.py          # 合并原 pipeline/models.py + transcribe 模型
│   ├── config.py          # 原 pipeline/config.py + transcribe/config.py
│   ├── helpers.py         # 原 pipeline/helpers.py
│   ├── preview.py         # 原 pipeline/preview.py
│   ├── preview_backfill.py # 原 pipeline/preview_backfill.py
│   ├── http.py            # 原 transcribe/http.py
│   ├── oss_sign.py        # 原 transcribe/oss_sign.py
│   ├── oss_upload.py      # 原 transcribe/oss_upload.py
│   ├── export_utils.py    # 原 transcribe/export_utils.py
│   ├── runtime.py         # 原 transcribe/runtime.py
│   ├── result_metadata.py # 原 transcribe/result_metadata.py
│   ├── error_classifier.py # 原 transcribe/error_classifier.py
│   └── errors.py          # 原 transcribe/errors.py
│
├── assets/                # 资源管理
│   ├── __init__.py
│   ├── service.py         # 业务逻辑（原 services/media_asset_service.py + asset_update_service.py）
│   ├── repository.py      # 数据访问（原 repositories/asset_repository.py）
│   ├── file_ops.py        # 文件操作（原 services/asset_file_ops.py）
│   ├── gc.py              # 垃圾回收（原 services/asset_gc.py + cloud_cleanup_service.py）
│   ├── local.py           # 本地资源（原 services/local_asset_service.py）
│   └── reconciler.py      # 对账（原 services/transcript_reconciler.py）
│
├── scheduler/             # 任务调度
│   ├── __init__.py
│   ├── base.py            # Worker 基类（原 workers/base.py）
│   ├── registry.py        # Worker 注册表（从 base.py 分离）
│   ├── dispatcher.py      # 任务分发（原 workers/task_dispatcher.py）
│   ├── queue.py           # 任务队列操作（新增，从 task_ops.py 抽取）
│   ├── ops.py             # 任务操作（原 services/task_ops.py 核心）
│   ├── state.py           # 任务状态（原 services/task_state.py）
│   ├── retry.py           # 自动重试（原 services/auto_retry.py）
│   ├── progress.py        # 进度构建（原 services/pipeline_progress.py）
│   ├── health.py          # 健康检查（原 services/health_check_service.py）
│   └── cleanup.py         # 任务清理（原 services/cleanup.py 任务相关部分）
│
├── api/                   # HTTP 入口
│   ├── __init__.py
│   ├── app.py             # FastAPI 应用组装
│   ├── schemas.py         # Pydantic schemas
│   └── routers/
│       ├── __init__.py
│       ├── assets.py      # 资源路由（从原 api/routers/assets.py 移入）
│       ├── creators.py    # 创作者路由（从原 api/routers/creators.py 移入）
│       ├── download.py    # 下载路由（合并原 douyin.py + bilibili.py 下载部分）
│       ├── metrics.py     # 指标路由
│       ├── scheduler.py   # 任务路由（从原 tasks.py 移入）
│       ├── search.py      # 搜索路由（跨域查询，保留在顶层）
│       ├── settings.py    # 设置路由
│       └── transcribe.py  # 转写路由
│
├── store/                 # 数据存储
│   ├── __init__.py
│   ├── db.py              # 数据库连接（原 db/core.py）
│   ├── fts.py             # 全文搜索（原 db/fts.py）
│   ├── path_utils.py      # 原 db/path_utils.py
│   └── models.py          # 数据模型（合并各 repository 的模型定义）
│
├── creators/              # 创作者管理
│   ├── __init__.py
│   ├── service.py         # 创作者业务逻辑
│   ├── repository.py      # 原 repositories/creator_repository.py
│   └── sync.py            # 同步逻辑（原 workers/creator_sync.py 业务部分）
│
├── accounts/              # 账号管理（从 transcribe/ 独立，因被多域使用）
│   ├── __init__.py
│   ├── service.py         # 原 services/account_pool_service.py
│   ├── repository.py      # 原 repositories/account_repository.py
│   └── status.py          # 原 services/qwen_status.py
│
└── core/                  # 核心基础设施
    ├── __init__.py
    ├── config.py          # AppConfig
    ├── exceptions.py      # 全局异常
    ├── events.py          # 事件系统
    ├── logging_context.py # 日志上下文
    ├── cookie_manager.py  # Cookie 管理
    ├── background.py      # 后台任务
    ├── task_progress.py   # 任务进度
    ├── workflow.py        # 工作流基础
    └── secure_storage.py  # 安全存储
```

## 文件迁移映射

### 删除的目录

| 目录 | 说明 |
|------|------|
| `src/media_tools/services/` | 职责拆分后不再存在 |
| `src/media_tools/workers/` | 骨架进 scheduler/，业务 worker 进 download/, transcribe/ |
| `src/media_tools/pipeline/` | 核心逻辑进 transcribe/，调度进 scheduler/ |
| `src/media_tools/repositories/` | 各 repository 随业务域拆分 |
| `src/media_tools/db/` | 移至 store/ |
| `src/media_tools/douyin/` | 下载相关进 platform/douyin.py，auth 进 download/ 或 platform/ |
| `src/media_tools/bilibili/` | 下载相关进 platform/bilibili.py |
| `src/media_tools/api/websocket_manager.py` | 移至 infra/（或保留在 api/ 作为薄包装） |

### 主要文件迁移

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `services/media_asset_service.py` | `assets/service.py` | 合并 asset_update_service |
| `services/asset_update_service.py` | `assets/service.py` | 合并入 assets/service |
| `services/asset_gc.py` | `assets/gc.py` | 合并 cloud_cleanup |
| `services/cloud_cleanup_service.py` | `assets/gc.py` | 合并入 assets/gc |
| `services/asset_file_ops.py` | `assets/file_ops.py` | |
| `services/local_asset_service.py` | `assets/local.py` | |
| `services/transcript_reconciler.py` | `assets/reconciler.py` | |
| `services/account_pool_service.py` | `accounts/service.py` | |
| `services/qwen_status.py` | `accounts/status.py` | |
| `services/transcribe_run_service.py` | `transcribe/runs.py` | |
| `services/task_ops.py` | `scheduler/ops.py` | queue/ops 拆分 |
| `services/task_state.py` | `scheduler/state.py` | |
| `services/auto_retry.py` | `scheduler/retry.py` | |
| `services/pipeline_progress.py` | `scheduler/progress.py` | |
| `services/health_check_service.py` | `scheduler/health.py` | |
| `services/cleanup.py` | `scheduler/cleanup.py` + `infra/cleanup.py` | 任务相关 vs 通用文件清理拆分 |
| `services/file_browser.py` | `infra/file_browser.py` | |
| `services/log_rotation.py` | `infra/log_rotation.py` | |
| `services/bilibili_nickname.py` | `platform/bilibili.py` | 合并 |
| `workers/base.py` | `scheduler/base.py` + `scheduler/registry.py` | 基类与注册表分离 |
| `workers/task_dispatcher.py` | `scheduler/dispatcher.py` | |
| `workers/pipeline_worker.py` | `download/worker.py` + `transcribe/worker.py` | DownloadWorker 归 download，转写 worker 归 transcribe |
| `workers/creator_sync.py` | `creators/sync.py` + `scheduler/` | 业务逻辑归 creators，worker 壳归 scheduler |
| `workers/creator_transcribe_worker.py` | `transcribe/worker.py` | 合并 |
| `workers/local_transcribe_worker.py` | `transcribe/worker.py` | 合并 |
| `workers/full_sync_worker.py` | `transcribe/worker.py` | 合并 |
| `workers/aweme_recover_worker.py` | `creators/sync.py` | 合并或独立 |
| `workers/transcribe.py` | `transcribe/worker.py` | 合并 |
| `pipeline/orchestrator.py` | `transcribe/service.py` | 转写调度核心 |
| `pipeline/worker.py` | `transcribe/worker.py` + `download/worker.py` | 拆分 |
| `pipeline/models.py` | `transcribe/models.py` | 合并 |
| `pipeline/error_types.py` | `transcribe/error_types.py` | |
| `pipeline/helpers.py` | `transcribe/helpers.py` | |
| `pipeline/config.py` | `transcribe/config.py` | 合并 transcribe/config |
| `pipeline/preview.py` | `transcribe/preview.py` | |
| `pipeline/preview_backfill.py` | `transcribe/preview_backfill.py` | |
| `pipeline/download_router.py` | `download/service.py` | |
| `pipeline/task_helpers.py` | `scheduler/ops.py` 或 `scheduler/helpers.py` | |
| `pipeline/media_extensions.py` | `transcribe/` 或 `core/` | |
| `repositories/asset_repository.py` | `assets/repository.py` | |
| `repositories/task_repository.py` | `scheduler/repository.py` | |
| `repositories/creator_repository.py` | `creators/repository.py` | |
| `repositories/account_repository.py` | `accounts/repository.py` | |
| `repositories/transcribe_run_repository.py` | `transcribe/runs.py` | 合并 |
| `db/core.py` | `store/db.py` | |
| `db/fts.py` | `store/fts.py` | |
| `db/path_utils.py` | `store/path_utils.py` | |
| `douyin/core/downloader.py` | `platform/douyin.py` | 合并 |
| `douyin/core/f2_helper.py` | `platform/douyin.py` | 合并 |
| `douyin/core/auth_server.py` | `platform/douyin.py` 或 `api/` | auth 路由 |
| `bilibili/core/downloader.py` | `platform/bilibili.py` | 合并 |
| `api/routers/assets.py` | `api/routers/assets.py` | 保留位置，内部 import 改 assets/ |
| `api/routers/creators.py` | `api/routers/creators.py` | 保留位置 |
| `api/routers/douyin.py` | `api/routers/download.py` | 合并 bilibili 下载路由 |
| `api/routers/bilibili.py` | `api/routers/download.py` | 合并 |
| `api/routers/tasks.py` | `api/routers/scheduler.py` | 重命名 |
| `api/routers/scheduler.py` | `api/routers/scheduler.py` | 已存在（原 scheduler 路由） |
| `api/routers/search.py` | `api/routers/search.py` | 保留 |
| `api/routers/settings.py` | `api/routers/settings.py` | 保留 |
| `api/routers/metrics.py` | `api/routers/metrics.py` | 保留 |
| `api/websocket_manager.py` | `infra/websocket.py` | 或保留在 api/ 做薄包装 |
| `core/secure_storage.py` | `core/secure_storage.py` 或 `infra/secure_storage.py` | |
| `common/paths.py` | `core/paths.py` 或 `store/path_utils.py` | 合并 |

## 配置与日志统一

### 配置现状

当前配置散落在至少 3 个位置：

| 位置 | 内容 | 问题 |
|------|------|------|
| `config/` | `config.yaml`, `auth_rules.yaml`, `active_preset.txt`, `transcribe/accounts.json`, `transcribe/.env` | 格式混乱（YAML + TXT + JSON + ENV） |
| `src/config/` | `active_preset.txt` | 与 `config/active_preset.txt` 重复 |
| `src/media_tools/config/` | `following.json` | 不应该在源码目录 |

**目标：** 所有运行时配置只存在于 `config/`，源码目录内不再有任何配置文件。

### 配置统一方案

```
config/                     # 唯一配置根
├── config.yaml            # 主配置（已有，保留并清理）
├── auth_rules.yaml        # 认证规则（已有，保留）
├── presets.yaml           # 合并 active_preset.txt（YAML 格式）
├── download.yaml          # 下载域配置（从 download 模块提取）
├── transcribe.yaml        # 转写域配置（从 transcribe 模块提取）
└── secrets/               # 敏感配置（gitignored，已有）
    ├── accounts.json      # 原 config/transcribe/accounts.json
    └── .env               # 原 config/transcribe/.env
```

**规则：**
- 所有配置统一用 YAML 格式（已有 JSON 的保持兼容但新配置用 YAML）
- `core/config.py` 作为统一配置加载入口，各模块不再自己读文件
- 删除 `src/config/` 和 `src/media_tools/config/` 目录
- `following.json` 移至 `config/` 或合并入 `config.yaml`

### 日志现状

当前日志分布在 **7 个位置**：

| 位置 | 内容 |
|------|------|
| `logs/` | `app.log`, `app.jsonl`, `f2-trace-*.log`（ hundreds of empty files） |
| `src/logs/` | 未知 |
| `src/media_tools/logs/` | 未知 |
| `frontend/logs/` | 前端日志 |
| `frontend/data/logs/` | 前端数据日志 |
| `data/logs/` | 数据日志 |
| `.git/logs/` | git 自身（不用管） |

**f2-trace 问题：** 每次下载尝试生成一个 `f2-trace-YYYY-MM-DD-HH-MM-SS.log`，一天产生几十个，绝大多数是 0 字节。

### 日志统一方案

```
logs/                       # 唯一日志根
├── app.log                 # 主应用日志（轮转）
├── app.jsonl               # 结构化日志（轮转）
├── download/
│   └── f2.log              # f2 下载日志（合并，按天轮转，不再按次）
├── transcribe/
├── scheduler/
└── archive/               # 自动归档（保留 7 天，超期删除）
```

**规则：**
- 所有业务日志写入 `logs/` 下对应子目录
- 删除 `src/logs/`, `src/media_tools/logs/`, `frontend/logs/`, `frontend/data/logs/`, `data/logs/`
- f2-trace 改为追加写入 `logs/download/f2.log`，由 Python 的 `logging` 模块统一轮转
- 前端日志如需保留，通过 API 写入后端统一日志，或单独配置到 `logs/frontend/`
- 日志轮转策略：`app.log` 和 `app.jsonl` 按天轮转，保留 7 天

## 测试重组

测试目录镜像源码结构：

```
tests/
├── conftest.py
├── platform/
│   ├── test_douyin.py
│   └── test_bilibili.py
├── download/
├── transcribe/
├── assets/
├── scheduler/
├── api/
├── store/
├── creators/
├── accounts/
└── core/
```

原有测试文件按测试目标移到对应目录。

## 添加新功能的路径

| 需求 | 操作 |
|------|------|
| 支持 YouTube | 加 `platform/youtube.py`，`download/service.py` 加平台选择 |
| 加字幕翻译 | 新建 `translate/service.py` + `translate/worker.py`，scheduler 注册 |
| 改下载并发 | 只改 `download/service.py` |
| 改转写重试 | 只改 `scheduler/retry.py` |
| 改资源展示 | 只改 `assets/service.py` + `api/routers/assets.py` |
| 改任务队列策略 | 只改 `scheduler/queue.py` |
| 新平台认证方式 | 只改 `platform/xxx.py` |

## 实施策略

分阶段执行，每阶段独立可验证：

**Phase 1: 基础设施迁移**
- `db/` → `store/`
- `common/` → `core/`
- `api/websocket_manager.py` → `infra/`
- 验证：所有测试通过

**Phase 2: services/ 拆分**
- 任务相关 → `scheduler/`
- 资产相关 → `assets/`
- 账号相关 → `accounts/`
- 转写相关 → `transcribe/runs.py`
- 通用工具 → `infra/`
- 验证：所有测试通过

**Phase 3: workers/ 与 pipeline/ 拆分**
- Worker 基类/注册表/分发器 → `scheduler/`
- DownloadWorker → `download/`
- 转写 workers → `transcribe/`
- Orchestrator → `transcribe/service.py`
- Pipeline worker → 拆分至 download/transcribe
- 验证：所有测试通过

**Phase 4: 平台模块合并**
- `douyin/` → `platform/douyin.py`
- `bilibili/` → `platform/bilibili.py`
- 验证：所有测试通过

**Phase 5: API 路由整理**
- 合并下载路由
- 更新所有 import
- 验证：所有测试通过 + 手动启动验证

**Phase 6: 配置/日志/测试清理**
- 统一配置目录
- 统一日志目录
- 重组测试目录
- 删除空目录和废弃文件
- 验证：所有测试通过

## 风险与应对

| 风险 | 应对 |
|------|------|
| import 遗漏导致运行时错误 | 每阶段改完后跑全部测试 + 手动启动服务验证 |
| 测试文件大量移动导致 git 历史丢失 | 使用 `git mv` 保持文件历史 |
| 某阶段改动太大难以回滚 | 每阶段独立 commit，阶段间可切分支 |
| 平台合并导致代码冲突 | 先抽公共接口 `platform/base.py`，再合并实现 |
| 循环依赖在迁移中暴露 | 提前画依赖图，发现反向依赖时引入接口层 |

## 验收标准

1. `src/media_tools/` 下不再存在 `services/`、`workers/`、`pipeline/`、`repositories/`、`db/`、`douyin/`、`bilibili/` 目录
2. 所有测试通过
3. 服务可正常启动，核心流程（下载+转写）手动验证通过
4. 新添加一个 mock 平台支持不超过 3 个文件改动
5. 配置文件只存在于 `config/`，日志只输出到 `logs/`
