# Media Tools — 项目现状文档

> 最后更新：2026-05-14

---

## 最近更新（2026-05-05）

## 最近更新（2026-05-12）

### 并发模型重设计 + 额度领取防御修复

- ✅ **per-account 上传互斥**：全局 `Semaphore(n_accounts)` 改为 `dict[account_id, asyncio.Lock]`。Qwen 平台约束同账号仅 1 个上传活跃，客户端用 Lock 显式串行，避免占额度空等。
- ✅ **AccountPool 简化**：去掉余额加权随机（平台已限单账号并发，余额不再影响调度），改为纯轮询 + 排除集。
- ✅ **删除 export_gate**：导出/下载阶段取消 Semaphore 限流，平台无明显并发约束。
- ✅ **入口闸门 = 2n**：`transcribe_batch` 的 Semaphore 大小由 `_adjust_gates_to_account_pool()` 设为 `2 * n_accounts`，跟随账号池自动伸缩。
- ✅ **OSS part_size = 5MB**：默认分片从 1MB 调到 5MB，减少 HTTP 往返；part 级并发 benchmark 证明带宽已饱和，保持串行。
- ✅ **额度领取 delta 兜底**：`claim_equity_quota` 触发后查 before/after 额度差，没增加就返回 `claimed=False`，避免"显示成功但未到账"。
- ✅ **`_current_account_id` 竞态修复**：移除实例变量，改参数传递，避免并发场景下 cleanup 用错 cookie
- ✅ **跨账号 cleanup 过滤**：`find_failed_record_ids` 增加 `account_id` 参数，只删当前账号记录
- ✅ **不吞中断信号**：`gather(return_exceptions=True)` 后重新 raise `BaseException`
- ✅ **resume record_id 缺失保护**：`_try_resume_export_only` 入口检查 record_id，避免孤儿记录

### Phase 4 — 可观测性（refactor 第四阶段）

- ✅ **失败原因聚合视图**：`/api/v1/metrics/failure-summary?days=N` + Settings 页 `FailureSummarySection`，按 error_type/error_stage 分桶；Top 错误一目了然
- ✅ **健康检查脚本**：`scripts/health_check.py` 检 4 类一致性问题；JSON 输出 + 退出码可接 cron
- ✅ **PARTIAL_FAILED 任务状态**：区分全失败/部分失败；前端 badge 中文化；UI"重试失败子任务"按钮在 PARTIAL 任务上正确显示
- ✅ **logs/ 归档机制**：`services.log_rotation.archive_old_logs()` mv 到 archive 子目录，不删
- ✅ **Ghost transcripts 清理**：`reconcile_transcripts()` 新增 prune 逻辑，清理 DB 中已完成但文件已不存在的"幽灵"记录

### Phase 3 — 可恢复转写流水线（重构第三阶段）

> 详细设计见 [pipeline_reliability_refactor.md](pipeline_reliability_refactor.md) 第 156–189 行。

**已落地：**

| 项目 | 内容 |
|------|------|
| `transcribe_runs` 表 | 每行 = 某 asset 在某账号上的一次完整转写尝试 |
| stage 推进序 | `queued → uploaded → transcribing → exporting → downloading → saved` |
| `find_resumable()` | gen_record_id 已持久化 + stage ∈ RESUMABLE，**或** stage='failed' 但 error_stage ∈ RESUMABLE |
| 续传 fast-path A | 已有 `export_url` → 直接 download，**0 调用 Qwen API** |
| 续传 fast-path B | 已有 `gen_record_id` → 跳过 token/upload/heartbeat/start，从 poll 继续 |
| 保险丝 | 续传任何异常 → stage 重置 `queued` → 完整 flow 接管 |
| 测试覆盖 | 13 个单元/集成测试（建表、stage 推进、续传命中、各级 fallback、E2E 失败 → 重试复用） |
| Ghost transcripts 清理 | reconciler 新增 prune 逻辑：completed 但文件已不存在时自动清理 DB 记录 |

**关键不变量**：跨账号续传**不**支持（Qwen `genRecordId` 与账号绑定）。

### Qwen 转写引擎完成迁移：Playwright → HTTP API

- 转写流程从 Playwright + Chromium 改为纯 HTTP 调用 `RequestsApiContext`
- 全仓清理 Playwright/Chromium 残留描述（README / CONTRIBUTING / FAQ / INSTALLATION / 用户手册 / 源代码注释）
- `tests/test_no_playwright_dependency.py` 强制守护，pyproject/requirements/src import 任一处出现 `playwright` 都 fail

### 文档与配置

- 新增 [CLAUDE.md](../CLAUDE.md) — 给 Claude Code 与未来贡献者的项目向导
- `_auto_*.json` per-creator 状态文件归档至 `.archive/pipeline_state_2026-04-26/`（无业务影响，全 ghost 状态）

---

## 最近更新（2026-04-20）

### 任务中心重构

**已完成的改进：**

| 功能 | 描述 |
|------|------|
| 清除历史优化 | 清除后不再从数据库恢复（前端 historyCleared 标记） |
| WebSocket 断连提示 | 红色提示条 + 侧边栏红点 |
| 简化重试按钮 | 失败任务只显示一个"重试"按钮 |
| 展开详情面板 | 点击任务卡片展开，显示详细信息 |
| 子任务列表 | 展示成功/失败/进行中的视频列表 |
| 状态标签友好化 | "可能中断"替代"已过期"等 |
| 后端 payload 结构化 | 支持 `result_summary` 和 `subtasks` 字段 |

**数据流架构：**

```
用户创建任务
     ↓
后端存储 payload（含 subtasks 列表）
     ↓
WebSocket 广播进度更新（含 result_summary）
     ↓
前端展示：成功 X / 失败 Y / 子任务列表
```

### 代码质量优化

**异常处理改进：**

| 指标 | 改进前 | 改进后 |
|------|--------|--------|
| 宽泛异常捕获 | 56 处 | 9 处 |
| 减少比例 | - | 84% |

**改进的异常类型：**

| 文件 | 改进 |
|------|------|
| `tasks.py` | sqlite3.Error, json.JSONDecodeError |
| `assets.py` | OSError, ValueError |
| `creators.py` | sqlite3.Error, OSError, ValueError |
| `db/core.py` | sqlite3.Error |
| `orchestrator_v2.py` | sqlite3.Error |
| `preview.py` | OSError, zipfile.BadZipFile, ET.ParseError |
| `downloader*.py` | OSError, ImportError, IOError |

**剩余 9 处合理保留：**
- Playwright 自动化（多种浏览器/网络异常）
- 数据库事务回滚（需要捕获所有异常确保回滚）
- 后台任务日志记录（已有 logger.exception）

### Inbox 三栏布局

- Apple Mail Pro 风格：创作者列表 + 素材列表 + 即时预览
- **本地素材独立入口**：黄色徽章标识，与博主列表分离
- 本地文件夹分组显示，支持展开/折叠
- 进入页面自动同步文件系统与数据库
- 主题切换按钮（深色/浅色模式）

### 素材来源

| 来源 | 说明 |
|------|------|
| 抖音创作者 | 通过主页 URL 添加，自动下载该创作者的视频 |
| B站 UP 主 | 通过空间链接添加，自动下载视频 |
| 本地素材 | 通过「本地转写」上传，**独立入口显示**，按文件夹分组 |

---

## 一、项目概况

抖音/B站视频批量下载 + 通义千问（Qwen）自动转写的 **Web 工作站**。

> **注意**：项目已完全迁移到 Web 界面，不再提供 CLI 交互模式。

| 维度 | 现状 |
|------|------|
| 后端 | FastAPI + Uvicorn，SQLite3（无 ORM），APScheduler 定时任务 |
| 前端 | React 19 + Vite 8 + Tailwind 4 + shadcn/ui + Zustand 5 |
| 视频抓取 | F2 库（抖音）+ yt-dlp（B站） |
| 转写引擎 | Qwen HTTP API（已从 Playwright 迁移，2026-05-05） |
| 实时通信 | WebSocket 推送任务进度 |
| Python | 3.9（`from __future__ import annotations` 已全仓铺开，但 `pipeline/preview.py:10` 的 `Path \| str` 写法仍触发运行时 TypeError，待修） |
| 启动方式 | `./run.sh`（后端 8000 + 前端 5173） |

### 素材来源

| 来源 | 说明 |
|------|------|
| 抖音创作者 | 通过主页 URL 添加，自动下载该创作者的视频 |
| B站 UP 主 | 通过空间链接添加，自动下载视频 |
| 本地文件 | 通过「本地转写」上传，**独立存储于文件夹分组中**，不归属于创作者 |

---

## 二、后端 API 端点清单

### 2.1 创作者 `/api/v1/creators`

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/creators/` | 列出所有创作者及资产统计 |
| POST | `/api/v1/creators/` | 通过主页链接添加创作者（抖音/B站） |
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

### 2.4 设置 `/api/v1/settings`

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/settings/` | 获取系统设置总览 |
| POST | `/api/v1/settings/douyin` | 添加抖音账号到账号池 |
| DELETE | `/api/v1/settings/douyin/{account_id}` | 移除抖音账号 |
| POST | `/api/v1/settings/bilibili/accounts` | 添加B站账号 |
| POST | `/api/v1/settings/qwen` | 保存 Qwen Cookie |
| POST | `/api/v1/settings/global` | 更新全局设置（并发/自动删除/自动转写） |

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

---

## 三、前端页面/路由清单

| 路由 | 页面组件 | 功能 |
|------|---------|------|
| `/` | → 重定向到 `/home` | — |
| `/home` | `Home.tsx` | 工作台：iOS Widget 风格仪表盘，实时任务进度、创作者概览、快捷操作 |
| `/library` | `Library.tsx` | 内容库：创作者网格、搜索、添加创作者 |
| `/settings` | `Settings.tsx` | 设置页：账号池（抖音/B站/Qwen）、Cookie、全局偏好、导出格式 |

### 布局组件

| 组件 | 位置 | 功能 |
|------|------|------|
| `Sidebar` | 全局左侧（桌面端） | 导航 + 主题切换 |
| `BottomNav` | 全局底部（移动端） | 导航 + 任务徽章 |
| `Widget` | Home 页面 | Small/Medium/Large 三种 iOS 风格卡片 |
| `WidgetGrid` | Home 页面 | 2×2/4 列自适应网格 |
| `AppleEmptyState` | 各页面 | 苹果风格空状态占位 |

---

## 四、数据库表结构（SQLite3）

| 表名 | 说明 |
|------|------|
| `creators` | 创作者信息（UID、昵称、平台、同步状态） |
| `media_assets` | 素材（视频/转写状态、本地路径、已读/收藏） |
| `transcribe_runs` | 每个 asset 在某账号上的一次转写尝试，支持续传（2026-05） |
| `task_queue` | 任务队列（类型、进度、状态、payload） |
| `auth_credentials` | 平台认证数据 |
| `Accounts_Pool` | 账号池（抖音/B站/Qwen Cookie） |
| `SystemSettings` | KV 形式全局设置 |
| `scheduled_tasks` | 定时任务（Cron 表达式、启用状态） |
| `assets_fts` | FTS5 全文搜索索引 |

---

## 五、已完成的改进

### 2026-05-05

- [x] Phase 4 可观测性：失败聚合 API + Settings 表格 / 健康检查脚本 / PARTIAL_FAILED 状态机
- [x] Ghost transcripts 清理：reconcile_transcripts() 新增 prune 逻辑
- [x] Phase 3 可恢复转写流水线（transcribe_runs 表 + find_resumable + 两条续传 fast-path）
- [x] Qwen 转写引擎完全迁移到 HTTP（去 Playwright/Chromium 依赖）
- [x] 全仓清理 Playwright 残留描述（5 个文档 + 4 个源/测试文件）
- [x] logs/ 改为归档不删（services/log_rotation.py + lifespan 接入）
- [x] 新增 CLAUDE.md 项目向导
- [x] 归档 4 个 Phase 2 之前的 _auto_*.json 孤儿状态文件

### 2026-04-20

- [x] 任务中心重构（清除历史、断连提示、子任务列表）
- [x] 异常处理优化（56 → 9 处，减少 84%）
- [x] Inbox 三栏布局 + 自动同步
- [x] 主题切换功能
- [x] 清理未使用文件

### 2026-04-15

- [x] 收件箱三栏布局重构
- [x] 本地文件夹分组
- [x] 数据库自动同步
- [x] Apple 设计语言
- [x] 双向同步完善
- [x] 批量操作优化

### 更早期

- [x] 统一数据库层
- [x] 清理 orchestrator（移除 V1）
- [x] 用 logger 替换 print
- [x] 修复双重 Toast
- [x] 清理死代码
- [x] CORS 收紧
- [x] 用 lifespan 替换 on_event

---

## 六、待改进项

> 优先级原则：**业务可靠性 > 工程规范**（详见 [CLAUDE.md](../CLAUDE.md)）。
> 这是单机本地工作台，不引入 CI/CD、Docker、覆盖率门槛、APM 等"生产服务"工程标准。

### P1 — 业务可靠性收尾（已闭环）

> Phase 1-4 全部落地，refactor 文档预设的所有路线图已交付（2026-05-05）。
> 继续重构需以**真实业务痛点**为驱动，而非工程惯性——参见 CLAUDE.md "业务可靠性 > 工程规范"。

- [x] ~~Phase 3 生产数据回放~~：手工演练，决定不安排（2026-05-05）；续传逻辑由 13 个单元/集成测试覆盖视为足够。

> `media_assets` 失败追踪字段（`transcript_last_error` / `transcript_error_type`
> / `transcript_retry_count` / `transcript_failed_at` / `last_task_id`）**已在
> Phase 2 通过 `_ensure_column` 加入并接通写入路径**（见 `db/core.py:507-513`），
> 不需要再 ALTER TABLE。

### P2 — 代码质量

- [ ] **Python 3.9 兼容**：`pipeline/preview.py:10` 的 `Path | str` 在 3.9 运行时触发 TypeError，需改为 `Union[Path, str]` 或加 `from __future__ import annotations`
- [ ] **额度领取真接口**：当前 trigger 调用的是 list 查询接口（历史 bug），需替换为 `/equity` 页面的实际 POST claim 接口（delta 兜底已做，替换后更直接）

### P3 — UI / 体验

- [x] **iOS Widget 风格前端重构**：像素级对齐 prototype.html，Apple 原生设计语言（2026-05-14）
- [ ] **前端测试**：补充 Vitest + React Testing Library（按需，不强求覆盖率）
- [ ] **Store 类型安全**：消除 `(taskUpdate as any).msg`
- [ ] **Settings 并发数校验**：程序化 clamp 到 1-10

### P3 — 长期愿景（不做明确投入，按需触发）

- [ ] **数据库迁移机制**：当 schema 变动频繁时考虑（SQLAlchemy 或简易迁移脚本）
- [ ] **多平台支持**：为小红书等平台预留扩展点
- [ ] **移动端适配**：响应式处理
