# Media Tools — 项目现状文档

> 最后更新：2026-07-01

> 这是一份**当前状态快照**。历史变更见 [CHANGELOG.md](../CHANGELOG.md)。

---

## 一、项目概况

抖音/B站视频批量下载 + 通义千问（Qwen）自动转写的 **Web 工作站**（单机本地部署，不提供 CLI 交互模式）。

| 维度 | 现状 |
|------|------|
| 后端 | FastAPI + Uvicorn、SQLite3（WAL，无 ORM）、APScheduler 定时任务 |
| 前端 | React 19 + Vite 8 + Tailwind CSS v4 + shadcn/ui + Zustand 5 + Framer Motion + @number-flow/react |
| 视频抓取 | f2（抖音）+ yt-dlp（B站） |
| 转写引擎 | Qwen HTTP API（已从 Playwright 迁移） |
| 实时通信 | WebSocket 推送任务进度（含心跳保活） |
| Python | 3.11+（`from __future__ import annotations` 全仓铺开，`str | None` 类型语法依赖此导入） |
| 启动方式 | `./run.sh`（后端 8000 + 前端 5173） 或 Docker（`docker compose up -d --build`） |
| 部署 | Docker 多阶段构建（frontend 编译 + Python 后端 + ffmpeg），`deploy/Dockerfile` + `deploy/docker-compose.yml` |
| CI | GitHub Actions（ruff lint + pytest） |
| Lint | ruff（check + format）+ mypy（可选）+ pre-commit hooks |

### 素材来源

| 来源 | 说明 |
|------|------|
| 抖音创作者 | 通过主页 URL 添加，批量下载视频 |
| B站 UP 主 | 通过空间链接添加，批量下载视频 |
| YouTube 频道 | 通过频道 URL 添加，批量下载视频 |
| 直接视频链接 | Discover 页面粘贴单个视频 URL（抖音/B站/YouTube），直接下载/转写 |
| 本地文件 | 通过「本地转写」上传，独立存储于文件夹分组中，不归属于创作者 |

---

## 二、后端 API 端点清单

### 2.1 创作者 `/api/v1/creators`

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/creators/` | 列出所有创作者及资产统计 |
| POST | `/api/v1/creators/` | 通过主页链接添加创作者（抖音/B站/YouTube） |
| DELETE | `/api/v1/creators/{uid}` | 删除创作者及全部关联资产 |

### 2.2 素材 `/api/v1/assets`

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/assets/` | 按创作者 UID 过滤素材列表 |
| GET | `/api/v1/assets/search` | 全文搜索素材 |
| GET | `/api/v1/assets/{asset_id}/transcript` | 获取转写文稿内容 |
| DELETE | `/api/v1/assets/{asset_id}` | 删除单个素材（含本地文件） |
| POST | `/api/v1/assets/bulk_delete` | 批量删除素材 |
| POST | `/api/v1/assets/bulk_mark` | 批量标记已读/收藏 |
| POST | `/api/v1/assets/export` | 导出转写文稿（ZIP） |

### 2.3 任务 `/api/v1/tasks`

| 方法 | 路径 | 用途 |
|------|------|------|
| WebSocket | `/api/v1/tasks/ws` | 实时任务进度推送 |
| POST | `/api/v1/tasks/pipeline` | 单创作者下载+转写全流水线 |
| POST | `/api/v1/tasks/pipeline/batch` | 批量视频 URL 下载+转写 |
| POST | `/api/v1/tasks/download/batch` | 批量仅下载 |
| POST | `/api/v1/tasks/download/creator` | 按创作者下载（增量/全量） |
| POST | `/api/v1/tasks/download/full-sync` | 全量同步所有关注创作者 |
| POST | `/api/v1/tasks/transcribe/local` | 本地文件转写 |
| POST | `/api/v1/tasks/reconcile-transcripts` | 同步文件系统与数据库 |
| GET | `/api/v1/tasks/active` | 获取活跃任务列表 |
| GET | `/api/v1/tasks/history` | 获取最近 50 条任务历史 |
| DELETE | `/api/v1/tasks/history` | 清除历史任务 |
| POST | `/api/v1/tasks/{task_id}/retry` | 重试失败任务 |
| POST | `/api/v1/tasks/{task_id}/rerun` | 重新运行任务 |
| POST | `/api/v1/tasks/{task_id}/cancel` | 取消任务 |
| DELETE | `/api/v1/tasks/{task_id}` | 删除任务 |
| POST | `/api/v1/tasks/{task_id}/auto-retry` | 启用/禁用自动重试 |
| PUT | `/api/v1/tasks/{task_id}/priority` | 更新任务优先级 |

### 2.4 设置 `/api/v1/settings`

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/settings/` | 获取系统设置总览 |
| POST | `/api/v1/settings/douyin` | 添加抖音账号到账号池 |
| DELETE | `/api/v1/settings/douyin/{account_id}` | 移除抖音账号 |
| POST | `/api/v1/settings/bilibili/accounts` | 添加B站账号 |
| POST | `/api/v1/settings/youtube/accounts` | 添加 YouTube 账号 |
| DELETE | `/api/v1/settings/youtube/accounts/{account_id}` | 移除 YouTube 账号 |
| PUT | `/api/v1/settings/youtube/accounts/{account_id}/remark` | 更新 YouTube 账号备注 |
| POST | `/api/v1/settings/qwen` | 保存 Qwen Cookie |
| POST | `/api/v1/settings/global` | 更新全局设置（自动删除/自动转写/导出格式） |

### 2.5 抖音元数据 `/api/v1/douyin`

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/douyin/metadata` | 获取创作者主页视频预览列表 |

### 2.6 定时任务 `/api/v1/scheduler`

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/scheduler/` | 列出所有定时任务 |
| POST | `/api/v1/scheduler/` | 添加定时同步（cron 表达式） |
| PUT | `/api/v1/scheduler/{task_id}/toggle` | 启用/禁用定时任务 |
| DELETE | `/api/v1/scheduler/{task_id}` | 删除定时任务 |

### 2.7 仪表盘 / 指标

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/dashboard` | 工作台综合数据（健康、任务、配额、失败摘要） |
| GET | `/api/v1/metrics/failure-summary?days=N` | 最近 N 天失败原因聚合 |
| GET | `/api/v1/transcripts` | 全局文稿列表（支持 `?status=all|unread|starred`） |

---

## 三、前端页面 / 路由清单

| 路由 | 页面组件 | 功能 |
|------|---------|------|
| `/` | → 重定向到 `/home` | — |
| `/home` | `Home.tsx` | 工作台：刊头 + 4 个 hero 数字（NumberFlow 滚动）+ 动态/快捷操作 + 创作者名册 + 失败摘要 + 最近文稿 |
| `/discover` | `Discover.tsx` | 发现：粘贴主页链接预览视频，勾选下载/转写 |
| `/library` | `Library.tsx` | 内容库：名册网格、搜索过滤、添加创作者、本地上传 |
| `/library/:creatorUid` | `CreatorDetail.tsx` | 创作者详情：素材列表（虚拟滚动）、转写阅读、批量操作、文件夹浏览 |
| `/transcripts` | `Transcripts.tsx` | 文稿库：左侧列表（未读/收藏过滤）+ 右侧阅读器 |
| `/tasks` | `Tasks.tsx` | 任务中心：4 个 hero 数字、tab 筛选、TaskItem 列表 |
| `/settings` | `Settings.tsx` | 账号池、Cookie、全局偏好、定时任务、系统清理 |

### 布局与组件

| 组件 | 位置 | 功能 |
|------|------|------|
| `AppLayout` | 全局布局 | 76px 字体导航栏（媒 logomark + 单字导航 + 时钟）+ 实时任务 ticker + Command Palette |
| `TranscriptReader` | 全屏阅读 | 文稿阅读器：TOC 侧栏、字号切换、上下篇导航、搜索、收藏、导出 |
| `TaskItem` | 任务中心 / 全局 | 任务行：状态点、阶段指示、进度 hairline、展开详情、重试 |
| `SkeletonScreen` | 路由 lazy fallback | 通用骨架屏 |

---

## 四、UI 设计语言

**Editorial Operations Studio** — 编辑式杂志风格的运营控制台。

| 维度 | 决策 |
|------|------|
| 色板 | 暖色近黑底 `#0c0b09` / 奶白文字 `#f3eedb` / 单一氧化铜锈色强调 `#c66b3e` |
| 状态色 | 古铜绿 `#87a878`（成功）/ 芥末黄 `#d4a850`（警告）/ 铁锈红 `#b25950`（失败） |
| 字体栈 | **Fraunces**（衬线显示，可变字重 + SOFT 轴）/ **Geist**（技术正文）/ **JetBrains Mono**（数据、ID、时间戳）/ **Noto Serif SC**（中文衬线） |
| 边角 | `--radius-card: 0` 锐利，分隔靠毛细线条（`rgba(243, 238, 219, 0.04 / 0.08 / 0.14)`）|
| 数字 | `@number-flow/react` 滚动动画，所有 hero 大数字（Home / Tasks）实时滚动 |
| 视觉密度 | 单语言（中文）、删除装饰性英文眉头；动作列表无序号；分隔靠 hairline + 留白 |
| 主题 | 仅暗色，不切换 |
| 字符 logomark | 衬线「**媒**」字（favicon 同款 SVG） |

---

## 五、数据库表结构（SQLite3）

| 表名 | 说明 |
|------|------|
| `creators` | 创作者信息（UID、昵称、平台、同步状态、`auto_sync` 自动同步标记） |
| `media_assets` | 素材（视频/转写状态、本地路径、已读/收藏、失败追踪字段） |
| `transcribe_runs` | 每个 asset 在某账号上的一次转写尝试，支持断点续传 |
| `task_queue` | 任务队列（类型、进度、状态、payload） |
| `auth_credentials` | 平台认证数据（兼容回退层，逐步废弃） |
| `Accounts_Pool` | 统一账号池（抖音/B站/Qwen Cookie + 状态） |
| `SystemSettings` | KV 形式全局设置 |
| `scheduled_tasks` | 定时任务（Cron 表达式、启用状态） |
| `assets_fts` | FTS5 全文搜索索引 |

---

## 六、关键设计决策

### 6.1 可恢复转写流水线

- **`transcribe_runs` 表**：每行 = 某 asset 在某账号上的一次完整转写尝试
- **Stage 推进**：`queued → uploaded → transcribing → exporting → downloading → saved`
- **续传 fast-path A**：已有 `export_url` → 直接 download，**0 调用 Qwen API**
- **续传 fast-path B**：已有 `gen_record_id` → 跳过 token/upload/heartbeat/start，从 poll 继续
- **保险丝**：续传任何异常 → stage 重置 `queued` → 完整 flow 接管
- **关键不变量**：跨账号续传**不**支持（Qwen `genRecordId` 与账号绑定）
- 13 个单元/集成测试覆盖

### 6.2 并发控制

| 层级 | 信号量 | 初始值 | 作用 |
|------|--------|--------|------|
| L1 | `_effective_concurrency` | Qwen 活跃账号数 | 同时处理的视频数 |
| L2 | `upload_gate` | 活跃账号数 | 同时上传到 Qwen 的数量 |
| L3 | per-account `asyncio.Lock` | 1 / 账号 | 同账号上传串行（平台约束） |

- AccountPool 纯轮询 + 排除集（余额加权已移除）
- OSS part_size = 5MB

### 6.3 错误重试策略

| 错误类型 | 行为 | 原因 |
|----------|------|------|
| `AUTH` | 切换账号，标记原账号 `expired` | Cookie 失效，需换号 |
| `QUOTA` | 切换账号，标记原账号 `rate_limited` | 额度耗尽，临时状态 |
| `SERVICE_UNAVAILABLE` (`recordStatus=40`) | **不切换账号**，保留原账号链路重试 | 平台级服务抖动，换号无用 |
| 其他 | 同账号重试（指数退避） | 网络/超时等瞬时问题 |

- 每次 `transcribe_with_retry` 重试前调用 `pool.reset_excluded()` 恢复被排除的账号
- `rate_limited` 状态的账号仍可被加载到账号池，不会被永久封禁

### 6.4 B站下载格式选择

yt-dlp 的 `format` 参数优先选择 H.264(AVC) 编码：

```
best[vcodec~='^avc']/bestvideo[vcodec~='^avc']+bestaudio/best/bestvideo+bestaudio
```

B站对大量视频提供 AV1 编码（压缩率更高但兼容性差），Qwen 听悟对 AV1 返回 `recordStatus=40`，因此强制 fallback 到 AVC。

### 6.5 YouTube 下载格式选择及代理说明

- **格式选择**：同 B 站一致，优先选择 H.264(AVC) 编码，避免音频/视频转写时出现解码器不支持问题。
- **代理支持**：由于网络限制，YouTube 下载与预解析需要通过代理进行。支持读取 `YOUTUBE_PROXY` 环境变量，无代理时自动回退使用 `BILIBILI_PROXY`。
- **扁平提取 (Preflight)**：在预解析频道信息（即获取频道名称创建对应本地目录）时，强制配置 `extract_flat: True`，以极速单次 HTTP 请求返回，避免访问每个视频详情页时触发人机/请求受限（Sign in to confirm you're not a bot）崩溃。

### 6.5 任务三态

- `COMPLETED`：全部成功
- `PARTIAL_FAILED`：部分子任务失败（前端显示「只重试失败」按钮）
- `FAILED`：全失败

---

## 七、待改进项

> 优先级原则：**业务可靠性 > 工程规范**。
> 这是单机本地工作台，不引入 Docker、覆盖率门槛、APM 等"生产服务"工程标准。

### P0 — 已修复的严重问题（2026-05-27）

- [x] **DB 连接 finally 关闭 Bug**：`platform/douyin.py` 三处 `finally: conn.close()` 会销毁线程缓存连接，已移除。
- [x] **异常类名冲突**：`PermissionError`/`ConfigurationError`/`TranscribeError` 三个类覆盖内建或跨模块同名冲突，已重命名为 `AccessDeniedError`/`AppConfigurationError`/`TranscribeApiError`。
- [x] **事务未回滚**：`delete_asset` 端点 `BEGIN IMMEDIATE` 后异常路径未回滚导致数据库锁死，已修复。

### P1 — 已修复的安全与架构问题（2026-05-27）

- [x] **路径注入防御**：`transcript_output_dir` API 设置增加项目目录白名单校验。
- [x] **Auth Server 请求体限制**：增加 10MB Content-Length 上限。
- [x] **架构耦合文档**：scheduler 层对 api/douyin 层的依赖点添加决策注释。

### P2 — 工程化基础设施（2026-05-27）

- [x] **CI 流水线**：`.github/workflows/ci.yml`（ruff lint + pytest）。
- [x] **Pre-commit hooks**：`.pre-commit-config.yaml`（ruff check + format）。
- [x] **pyproject.toml 工程化**：dev extra、ruff 配置、mypy 配置。
- [x] **依赖同步**：`requirements.txt` 与 `pyproject.toml` 对齐，移除死依赖 `questionary`/`requests`。
- [x] **死代码清理**：501 端点、空函数、未使用变量/导入、重复常量定义。
- [x] **日志系统合并**：`StructuredFormatter` 合并为 `JsonFormatter` 子类。

### P2 — 代码质量

- [ ] **额度领取真接口**：当前 trigger 调用的是 list 查询接口（历史 bug），需替换为 `/equity` 页面的实际 POST claim 接口（delta 兜底已做，替换后更直接）
- [x] **Store 类型安全**：已消除 `(taskUpdate as any).msg` 及 Settings 相关组件的 Props 类型错配（`editingRemark` 结构体、`handleClaimQuota` 签名、`ConfirmDeletePayload` 接口等），前端 `npm run build` 零报错。

### P2 — 测试与稳定性

- [x] **全量 Bug 审计与修复**：完成系统性盘查，修复 20+ 处缺陷（Python 3.9 兼容性、变量遮蔽、缓存污染、缺少导入、连接缓存隔离、命名冲突、事务提交遗漏、列缺失防御、竞态条件等），测试套件从多失败修复至 302 passed / 3 skipped / 0 failed。

- [x] **Docker 生产部署**：`deploy/Dockerfile` 多阶段构建（frontend 编译 + Python 后端 + ffmpeg），`deploy/docker-compose.yml` 一键拉起，访问 `http://localhost:8000` 即可使用。

### P3 — UI / 体验

- [x] **Settings 页编辑式重设计**：已通过模块化拆分（AccountExpandable, PreferenceSettingsSection, ScheduleSettings等）与样式对齐完成编辑式重构，使代码完全符合 300 行以下规范，并解决备注状态隔离回归问题。
- [ ] **前端测试**：补充 Vitest + React Testing Library（按需，不强求覆盖率）
- [ ] **移动端适配**：当前桌面优先，窄屏 grid 会塌

### P3 — 长期愿景（不做明确投入，按需触发）

- [ ] **数据库迁移机制**：当 schema 变动频繁时考虑（SQLAlchemy 或简易迁移脚本）
- [x] **Docker 部署**：Dockerfile + docker-compose 已就绪，见 `deploy/` 目录。
- [ ] **多平台支持**：为小红书等平台预留扩展点
