# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目性质

单机本地 Web 工作站：抖音/B站批量下载 → 通义千问云端转写 → 本地阅读管理。**没有部署、没有团队、没有 SLA** —— 不要套用"生产服务"的工程标准（CI/CD、Docker、覆盖率门槛在这里都是负收益）。优先级永远是**业务可靠性 > 工程规范**。

## 常用命令

```bash
./run.sh                # 同时启动后端 (8000) 和前端 (5173)
./run.sh backend        # 只启后端
./run.sh frontend       # 只启前端
./run.sh build          # 前端生产构建到 frontend/dist/
```

> README/CONTRIBUTING 里写的 `./run.sh setup` 和 `./run.sh test` **并不存在**，是文档残留。下面是真命令。

```bash
# 测试（pyproject.toml 已配 pythonpath=src, testpaths=tests）
pytest                                              # 全量
pytest tests/test_flow_resume.py                    # 单文件
pytest tests/test_flow_resume.py::test_xxx          # 单用例
pytest -k "transcribe and resume"                   # 关键字过滤
pytest -x --ff                                      # 失败立刻停 + 上次失败的先跑

# Lint（无 CI，但 ruff 已在 .ruff_cache 中用过）
ruff check src/
ruff format src/

# 前端
cd frontend && npm run dev
cd frontend && npm run build
cd frontend && npm run lint
cd frontend && npx vitest                           # 前端测试（vitest.config.ts 已配）
```

后端入口：`PYTHONPATH=src python -m uvicorn media_tools.api.app:app --reload`。

## 架构核心（必须先理解）

### 真相源分层
1. **业务真相源** = `data/media_tools.db`（SQLite, WAL）。`media_assets` 表的 `transcript_status` / `download_status` 才决定业务是否完成；任务（`task_queue`）只是"一次执行尝试"。
2. **运行时配置真相源** = `SystemSettings` 表（KV）。`auto_transcribe`、`auto_delete`、`api_key`、`export_format` 全在这里，**不要回去读 `config.yaml`**。`config.yaml` 只剩 `cookie` / `download_path` / `naming` 这种启动期常量。`concurrency` 字段仍存在但仅作内部参考值，**实际转写并发数由 Qwen 账号池大小决定**（`effective_concurrency = n_accounts`），见 `_adjust_gates_to_account_pool()`。前端已移除并发数输入框。
3. **转写阶段真相源** = `transcribe_runs` 表（2026-05 新加）。每行 = 某 asset 在某账号上的一次完整尝试，stage 推进序：`queued → uploaded → transcribing → exporting → downloading → saved`。

### 重构脉络
[docs/pipeline_reliability_refactor.md](docs/pipeline_reliability_refactor.md) 是 pipeline 改造的完整设计文档，**第一到第四阶段全部落地（2026-05-05）**：视频级状态治理 → 可恢复转写流水线 → 可观测性（失败聚合 / 健康检查 / PARTIAL_FAILED / 日志归档）。改 pipeline / orchestrator / transcribe 前必读，尤其是第 156-189 行的"Phase 3 已完成机制"——续传不变量在那里。

### 续传 fast-path（重要不变量）
`find_resumable(asset_id, account_id)` 命中条件：`gen_record_id` 已持久化，且 stage ∈ RESUMABLE_STAGES，**或** stage='failed' 但 `error_stage` ∈ RESUMABLE_STAGES。命中后：
- 已有 `export_url` → 直接 download，**0 调用 Qwen**
- 已有 `gen_record_id` → 跳过上传，从 `poll_until_done` 继续
- **不支持跨账号续传**（Qwen 的 `genRecordId` 与账号绑定）
- 续传任何异常 → stage 重置 `queued` → 完整 flow 接管（保险丝在 [orchestrator.py](src/media_tools/pipeline/orchestrator.py)）

### 模块布局（big-picture）

```
api/app.py            FastAPI 入口：lifespan 里做 init_db / FTS 填充 / 启动 scheduler /
                      cleanup_stale_tasks(is_startup=True)（重启后用特定错误信息标记孤儿任务）/ WS 半开扫除
api/routers/          7 个路由：creators assets tasks settings douyin scheduler metrics
api/websocket_manager 任务进度推送 + 心跳保活 + stale_connection_sweeper

pipeline/orchestrator.py  (871 行) 单创作者下载+转写主调度，账号池决策 + 重试 + 续传
pipeline/worker.py            后台 worker
pipeline/error_types.py       8 种错误分类 → 决定重试策略
pipeline/state_manager.py     Pipeline 断点续传状态管理
transcribe/flow.py            Qwen 实际转写流程；现已支持 resume 分支
transcribe/error_classifier.py 错误分类器：提供友好错误消息和操作建议
transcribe/db_account_pool    Qwen 账号池（DB 持久化）

core/cookie_manager.py  统一 Cookie 管理接口（三平台读取/轮换/标记）
core/secure_storage.py  Fernet 对称加密（Cookie 加密能力已就绪，暂未启用）

repositories/         数据访问层（task / creator / asset / transcribe_run）
services/             业务逻辑层；task_ops / cleanup / auto_retry / qwen_status / reconciler
services/pipeline_progress.py 进度构建：标准化 API 响应结构（阶段标签/图标/消息）
workers/              一次性后台任务（creator_sync / full_sync / local_transcribe ...）
core/config.py        运行时配置 = SystemSettings；不要绕过
core/background.py    后台 task registry（shutdown 时统一 cancel_all）
core/exceptions.py    AppError / NotFoundError / ValidationError → 统一 JSON 响应
db/core.py            连接（线程级缓存 + WAL）+ 标识符白名单（防 SQL 注入）
                      _VALID_TABLES 白名单：新加表必须加进去
```

### 错误处理模式
- 业务异常抛 `AppError` 子类（[core/exceptions.py](src/media_tools/core/exceptions.py)），由 `app_error_handler` 转 JSON。
- 路由里**不要**写宽泛 `try/except Exception` —— `UnhandledApiErrorsMiddleware` 已统一兜底 `sqlite3.Error / OSError / RuntimeError`。
- 之前一轮重构把宽泛捕获从 56 处砍到 9 处，**别再加回来**。捕获就要写具体异常类型。

### 硬约束（被测试强制）
- **不准用 `print`** —— [test_no_print_in_src.py](tests/test_no_print_in_src.py) 会全仓扫描，用 `media_tools.logger.get_logger`。
- **不准引入 Playwright** —— [test_no_playwright_dependency.py](tests/test_no_playwright_dependency.py) 扫 `pyproject.toml` / `requirements.txt` / 全部 src import。Qwen 转写已迁移成纯 HTTP，不要回退。（README 里"Playwright 驱动通义千问 Web 端"是过时描述。）
- 新增表必须加进 `db/core.py` 的 `_VALID_TABLES` 白名单。

### 任务状态机要点
- 任务 `RUNNING` ≠ 业务进行中。重启时所有内存 worker 丢失，但 DB 还残留 `RUNNING` —— `cleanup_stale_tasks(is_startup=True)` 在 startup 把它们标 FAILED，错误信息为"服务重启导致任务中断，请点击重试恢复。"，前端会显示琥珀色醒目横幅和一键重试按钮。
- 子任务（subtasks）才是业务真相，任务状态由子任务聚合。`PARTIAL_FAILED` **已显式支持**（2026-05-05），区分"全失败" vs "部分失败"，**不**触发 auto_retry 整任务（避免重跑成功子任务）；前端在 PARTIAL 任务上显示"重试失败子任务"按钮、隐藏"重试整任务"按钮。

## 协作约定

- 中文注释、中文 commit message（仓库现有风格：`feat(transcribe): ...`、`fix(pipeline): ...`）。
- 注释只解释 **WHY**，不解释 WHAT。
- 别为还没出现的需求做抽象。三行重复优于过早抽象。
- 改 pipeline / orchestrator / transcribe 前先看 [docs/pipeline_reliability_refactor.md](docs/pipeline_reliability_refactor.md) 第 156-189 行的"已完成机制"，确认你的改动不破坏续传不变量。
- [docs/STATUS.md](docs/STATUS.md) 已同步到 2026-05-05（含 Phase 3/4 细节）；任何文档都可能再次漂移，涉及当前进度的判断以代码 + `git log` 为准。

## 领域驱动架构（2026-05 新增，与上方模块布局并存）

> **注意**：上方"模块布局"描述的是按功能域组织的传统目录（`api/`、`pipeline/`、`services/` 等），下方 DDD 架构描述的是新增的分层目录（`domain/`、`infrastructure/`、`application/`、`presentation/`）。两套目录**同时存在**于 `src/media_tools/` 下。新功能优先使用 DDD 架构，旧功能通过 `migration/` 适配层桥接。

### 架构分层

| 层级 | 职责 | 特点 |
|------|------|------|
| **core** | 核心基础设施 | 配置、日志、异常处理；无外部依赖 |
| **domain** | 领域层 | 实体、仓储接口、领域服务；仅依赖 core |
| **infrastructure** | 基础设施层 | 数据库实现、外部 API 集成；依赖 domain + core |
| **application** | 应用层 | 业务管道、工作流编排；依赖 domain + core |
| **presentation** | 表示层 | REST API、WebSocket；依赖 application + domain |

### 核心优势

- **职责分离**：实体、仓储、服务明确分离，单一职责原则
- **依赖倒置**：高层模块不依赖低层模块，两者都依赖抽象接口
- **可测试性**：依赖注入设计，易于 Mock 测试
- **可扩展性**：插件化架构，易于添加新功能和替换实现
- **向后兼容**：通过迁移适配层实现平滑过渡

### 领域层结构

```
domain/
├── entities/           # 领域实体（富领域模型）
│   ├── Asset          # 素材实体（含业务方法）
│   ├── Creator        # 创作者实体
│   ├── Task           # 任务实体
│   └── Transcript     # 转写实体
├── repositories/       # 仓储接口（抽象数据访问）
│   ├── AssetRepository
│   ├── CreatorRepository
│   ├── TaskRepository
│   └── TranscriptRepository
└── services/           # 领域服务（封装业务逻辑）
    ├── AssetDomainService
    ├── CreatorDomainService
    └── TaskDomainService
```

### 领域实体

**Asset（素材实体）** - 核心业务模型：
- `mark_downloaded()` - 标记下载完成
- `mark_transcribed()` - 标记转写完成
- `mark_failed()` - 标记失败状态

**Creator（创作者实体）** - 创作者信息：
- `increment_downloaded()` - 增加下载计数
- `increment_transcript()` - 增加转写计数

**Task（任务实体）** - 任务管理：
- `start()` / `complete()` / `fail()` / `cancel()` - 状态转换
- `update_progress()` - 更新任务进度

### 仓储接口

定义数据访问抽象，不依赖具体实现：

```python
class AssetRepository(ABC):
    def save(self, asset: Asset) -> None: ...
    def find_by_id(self, asset_id: str) -> Optional[Asset]: ...
    def find_by_creator(self, creator_uid: str) -> List[Asset]: ...
    def delete(self, asset_id: str) -> None: ...
```

### 领域服务

封装跨实体的业务逻辑，不包含基础设施细节：

```python
class AssetDomainService:
    def __init__(self, asset_repo: AssetRepository, creator_repo: CreatorRepository): ...
    def create_asset(self, creator_uid: str, title: str) -> Asset: ...
    def mark_downloaded(self, asset_id: str, video_path: Path) -> None: ...
    def mark_transcribed(self, asset_id: str, transcript_path: Path, preview: str) -> None: ...
```

### 基础设施层

```
infrastructure/
└── db/                 # SQLite 仓储实现
    ├── create_asset_repository()
    ├── create_creator_repository()
    ├── create_task_repository()
    └── create_transcript_repository()
```

### 应用层

```
application/
└── pipelines/          # 业务管道
    ├── VideoDownloadPipeline
    ├── TranscribePipeline
    └── ExportPipeline
```

### 表示层

```
presentation/
├── api/
│   └── v2/             # v2 API 路由
│       ├── assets.py
│       ├── creators.py
│       └── tasks.py
└── websocket/          # WebSocket 管理
    └── manager.py
```

### 迁移适配层

`migration/__init__.py` 提供旧服务到新架构的桥接，保持向后兼容：

```python
# 旧服务调用新架构的适配层
from media_tools.migration import migrate_asset_service
asset_service = migrate_asset_service()  # 返回适配后的服务
```

### 迁移策略

旧服务层（`services/task_service.py`、`services/creator_service.py`、`services/asset_service.py`）已通过迁移适配层调用新架构，保持向后兼容。新代码应直接使用领域服务：

```python
# 新代码使用方式
from media_tools.domain.services import AssetDomainService
from media_tools.infrastructure.db import create_asset_repository, create_creator_repository

asset_service = AssetDomainService(
    create_asset_repository(),
    create_creator_repository(),
)
asset = asset_service.get_asset(asset_id)
```

### v2 API

新的 v2 API 路由已注册到主应用，路径前缀 `/api/v2/`，包括：
- `/api/v2/assets` - 素材管理
- `/api/v2/creators` - 创作者管理  
- `/api/v2/tasks` - 任务管理

### 新代码开发规范

1. **新功能**：直接使用 `domain/services` + `infrastructure/db`
2. **修改旧功能**：优先迁移到新架构，保持适配层兼容
3. **测试**：对领域服务进行单元测试，Mock 仓储接口
4. **依赖注入**：通过工厂函数创建仓储实例，避免硬编码

---

## 前端苹果设计风格重构（2026-05）

### 设计规范

#### 色彩系统

| 色彩类型 | 浅色模式 | 深色模式 | 说明 |
|---------|---------|---------|------|
| **背景** | `#F5F5F7` | `#1C1C1E` | Apple 标志性背景色 |
| **卡片** | `#FFFFFF` | `#2C2C2E` | 毛玻璃效果容器 |
| **主色** | `#007AFF` | `#0A84FF` | Apple 蓝 |
| **成功** | `#34C759` | `#30D158` | 绿色强调 |
| **警告** | `#FF9F0A` | `#FFD60A` | 橙色强调 |
| **危险** | `#FF3B30` | `#FF453A` | 红色强调 |
| **文字主色** | `#1D1D1F` | `rgba(255,255,255,0.9)` | 主体文字 |
| **文字次要** | `#86868B` | `rgba(255,255,255,0.55)` | 辅助文字 |

#### 字体层级

| 层级 | 大小 | 字重 | 行高 | 用途 |
|-----|------|------|------|------|
| H1 | 28px | 600 | 1.2 | 页面标题 |
| H2 | 22px | 600 | 1.25 | 区块标题 |
| H3 | 17px | 600 | 1.3 | 卡片标题 |
| Body | 15px | 400 | 1.4 | 正文内容 |
| Caption | 13px | 400 | 1.4 | 辅助说明 |
| Small | 11px | 500 | 1.5 | 标签/状态 |

#### 圆角规范

| 组件类型 | 圆角值 |
|---------|--------|
| 按钮/输入框 | 10px |
| 卡片 | 14px |
| 弹窗/模态框 | 20px |
| 圆形按钮 | 9999px |

#### 动画曲线

- **Spring 弹性**：`cubic-bezier(0.34, 1.56, 0.64, 1)` - 用于突出的交互动画
- **Subtle**：`cubic-bezier(0.25, 0.1, 0.25, 1)` - 用于次要过渡

### 组件重构

#### Button 组件
- 添加新变体：`ghostDestructive`、`linkSecondary`
- 添加新尺寸：`iconSm`、`iconLg`
- 添加按压缩放效果（`active:scale-[0.96]`）
- 使用 Spring 动画曲线

#### Card 组件
- 添加 `hoverable` 属性控制悬停效果
- 添加 `glass` 属性启用毛玻璃效果
- 悬停时上移并增强阴影

#### Input 组件
- 添加 `showClear` 属性支持一键清除
- 聚焦时添加光晕效果
- 优化 padding 和圆角

#### Switch 组件（新增）
- 苹果风格圆润滑块设计
- 平滑过渡动画

#### Badge 组件
- 优化字体大小（11px）
- 添加 `size` 变体
- 药丸形状设计

### 布局组件

#### Sidebar
- 毛玻璃背景效果（`backdrop-blur-2xl`）
- 品牌图标（渐变背景）
- 选中状态发光效果
- 优化导航项间距

#### AppLayout
- 页面过渡动画（`apple-slide-in-right`）
- 玻璃效果头部
- 统一页面标题样式

### 页面优化

#### CreatorCard
- 使用 Card 组件
- 图标统计（素材/已转写/待处理）
- 列表项悬停效果

#### GlobalSettingsSection
- 使用 Card 组件
- 苹果风格列表项
- Switch 开关组件

#### AccountPoolSection
- 使用 Card 组件
- 列表项悬停效果
- 优化状态标签

### 工具类

```css
/* 毛玻璃效果 */
.apple-glass-sidebar
.apple-glass-card  
.apple-glass-modal
.apple-glass-bar

/* 阴影效果 */
.apple-shadow-xs/sm/md/lg/xl

/* 动画效果 */
.apple-fade-in
.apple-slide-in-right  
.apple-scale-in
.apple-slide-up

/* 交互效果 */
.apple-press
.apple-card-hover
.apple-active-glow
.apple-list-item
```

### 响应式适配

- **Touch 目标**：按钮最小尺寸 44px
- **Safe area**：移动端底部安全区域适配
- **Toast 定位**：移动端全屏宽度

### 开发规范

1. **新组件**：使用苹果设计风格变量
2. **旧组件升级**：逐步迁移到新样式
3. **动画**：使用 Spring 曲线实现自然动效
4. **一致性**：保持视觉风格和交互模式统一
