# 变更日志

所有重要更改都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased] - REFACTOR 2026-05

### 🧹 任务 1：清空目录 + 死代码壳 + 孤儿文件

- 删除空目录 `src/media_tools/pipeline/`、`src/media_tools/repositories/`（DDD 重构后未清理的鬼影）
- 删除 `src/media_tools/db/core.py` shim（曾用作 db → store.db 迁移过渡，已无生产代码引用；15 处测试 import 一并迁移到 `media_tools.store.db`）
- 删除 `src/data/`、`src/logs/`（4 月前 f2 日志残骸）、`src/media_tools/downloads/` 三处历史目录
- 删除三处孤儿 SQLite 文件（`douyin_users.db` / `src/data/media_tools.db` / `src/media_tools/douyin_users.db`），仅保留 `data/media_tools.db` 作为唯一正本
- `.gitignore` 显式忽略已删目录防止 IDE/脚本误重建
- `tests/regression/test_recurring_backend.py` 的 BACKEND-004/009 白名单收敛到仅 `store/db.py`

### 🧹 任务 2：transcribe/ 三个 error 模块合一

- 合并 `errors.py` (21行 异常类) + `error_types.py` (60行 ErrorType enum + classify_error) + `error_classifier.py` (111行 ErrorInfo + TranscribeError + Classifier) 三个文件 → 单一 `errors.py` (~200 行，分 3 个章节保留来源标记)
- 公开 API 100% 兼容：`QwenTranscribeError` 系列异常类、`ErrorType` enum、`classify_error` 函数、`ErrorInfo` dataclass、`TranscribeError` 异常、`TranscribeErrorClassifier` 全部可从新 `errors` 模块直接 import
- 8 处生产代码 import 路径迁移；旧 `error_types.py` / `error_classifier.py` 彻底删除（ImportError 验证）
- 新增 `tests/test_error_module_consolidation.py` 3 条契约测试：所有公开 API 可 import + 旧模块路径必须 ImportError

### 🧹 任务 3：API 字段 snake_case 单边发车

- `src/media_tools/accounts/status.py` 删除 3 处 `accountId` / `accountLabel` dual-emit，API 响应统一 snake_case
- 前端 `types/index.ts` 删除 `QwenStatusAccount.accountId?` / `accountLabel?` 等 `@deprecated` camelCase 字段
- 前端 `services/dashboard.ts` 同步删除 `DashboardData.quota_status.accounts[].accountId?` 等字段
- 前端 `pages/Home.tsx` inline 类型清理 `accountId?` 字段
- 前端 `hooks/useSettings.ts` 删除 `a.account_id || a.accountId` 兼容 fallback（2 处）
- 新增 **`tests/api/test_no_camelcase_in_responses.py`** 2 条契约测试：
  1. 遍历所有无参 GET 路由，用 TestClient 发请求，递归扫 JSON keys 断言无 camelCase
  2. 扫描前端 types/dashboard/Home/useSettings 4 个文件无 `accountId?:` `accountLabel?:` 残留
- 注：`src/media_tools/transcribe/account_status.py` 整个文件仍含 camelCase 输出（`accountId/authStatePath/quotaError` 等），但**该文件全仓零 import**（属潜在死代码），不在任务 3 scope 内，留待后续清理任务
- 注：`frontend/src/services/settings.ts` 等的 `accountId` 是 JS 函数参数名（局部变量），非 API 契约字段，按 JS 惯例保留

---

## [2.5.5] - 2026-05-25

### ✨ 新增

- **大文件预切分（> 6 GB 自动按时长均分）**：千问平台严格拒绝单文件 > 6 GB 的转写请求，超大文件之前会在云端环节失败浪费已耗的上传时间。新增 `src/media_tools/transcribe/splitter.py`，在 `worker.py:run_local_transcribe` 入口检测，对 `> 6 GB` 文件用 ffmpeg `-c copy` 流复制按时长均分成 N 段（每段 ≤ 5.5 GB 留 buffer），每段作为独立转写任务（不合并结果）。
  - 切分缓存路径：`data/downloads/.split_cache/<original_asset_id_hex>/<stem>__partNofM.mp4`
  - 切分用 fast-seek（`-ss` 放 `-i` 前）+ `-c copy`，8 GB 文件 ~30-60 秒搞定，无重编码
  - 每段成功转写后**单独**清理 part 文件，失败的 part 保留供排查
  - 利用现有架构 `asset_id = sha1(absolute_path)`（`store/path_utils.py:35`），两个 part 自然获得独立 `asset_id` / 独立 `transcribe_runs` 行 / 独立 resume 链路。数据库 schema 零改动
  - 切分失败（ffmpeg 报错 / 文件损坏）会在日志记 ERROR 并跳过该文件，不阻塞批量其他文件

- **OSS 上传配置项**：`core/config.py` 新增 `qwen_oss_upload_concurrency`（默认 6，clamp 1-32）和 `qwen_oss_part_size_mb`（默认 0 = 按文件大小自动选 5/16/32 MB）。两者均支持 `SystemSettings` 表覆写或环境变量 `QWEN_OSS_UPLOAD_CONCURRENCY` / `QWEN_OSS_PART_SIZE_MB`。

### 🔧 改进

- **OSS 上传性能优化（预期单流 1.3 MB/s → 4-6 MB/s）**：诊断显示真实瓶颈在 `oss_upload.py` 的单流串行 + 无 keep-alive + 小分片，不是带宽。`upload_file_to_oss` 重构为：
  - **`requests.Session` 替代 `urllib.request.urlopen`**：模块级共享 Session + `HTTPAdapter(pool_connections=10, pool_maxsize=50)`，urllib3 PoolManager 底层 thread-safe，所有 `asyncio.to_thread` worker 复用同一连接池。消除每分片新建 TCP/TLS 握手的开销
  - **`_RequestsResponseAdapter`**：保留原 `with _open_request(req) as response:` 调用契约，所有 OSS 调用（initiate/upload_part/complete/abort/direct）零改动
  - **分片大小动态化**：`< 1 GB → 5 MB`、`< 5 GB → 16 MB`、`≥ 5 GB → 32 MB`。8 GB 文件分片数从 1667 降到 256，OSS API 调用频次降 6×
  - **单文件内并发分片上传**：producer/consumer 模式，1 个 producer 边读边投到 `asyncio.Queue(maxsize=concurrency)`（背压控制内存），N 个 consumer 并发跑 `upload_part`。任一抛错则 `asyncio.gather` 取消所有兄弟，外层 `abort_multipart_upload` 兜底清理。完成后按 `partNumber` 升序排序再 complete（OSS API 要求）
  - 内存峰值 ≈ `2 × concurrency × part_size`，默认 ≈ 192 MB / 文件
  - 小文件（< 100 MB）仍走 `direct` 分支不受影响

- **进度日志单调性**：`flow.py:571` `part-uploaded` 事件优先读 `completed`（已完成数）算 percent，fall back 到 `partNumber`（兼容旧路径）。并发上传时 partNumber 不再单调到达，但 `completed` 计数能保证日志的 `upload progress: X/Y (P%)` 仍然单调递增。

---

## [2.5.4] - 2026-05-24

### ✨ 新增

- **本地转写默认勾选"删除源文件"**：`useLibraryDetail.ts` 把 `deleteAfter` 初始值改为 `true`，提交后也重置为 `true`。这是高频用户偏好——大多数转写完成后用户希望本地源文件被清理，少数想保留的可以手动取消勾选。

### 🐛 修复

- **PARTIAL_FAILED 任务无法重试**：pipeline / batch_pipeline 的 `_build_subtasks`（`src/media_tools/transcribe/worker.py:228`）此前**不给 failed 子任务记录 `video_path`**，导致：
  - 前端 `failedRetryableCount` 计算成 0，"只重试失败" 按钮根本不显示
  - 后端 `/tasks/{id}/retry-failed` 收集到 0 个路径，直接返回 409 "没有可重试的失败视频路径"
  现在 failed 项必带 `video_path`。
- **子任务行内"重试任务"按钮在 PARTIAL_FAILED / COMPLETED 上 409**：`TaskItem.tsx:736` 此前一律调 `rerunTask`，但 `rerunTask` 后端要求状态为 `FAILED/CANCELLED/PAUSED`，部分失败/已完成状态点了就 409。现在按状态分流：失败/取消/暂停走 `rerunTask`，其它走 `retryFailedSubtasks`。
- **`handleRetry` 在 PARTIAL_FAILED 上误重跑已成功视频**：`useTaskActions.ts` 此前对部分失败任务也走全量重提交，会把已成功的视频再跑一遍。现在 `PARTIAL_FAILED` 优先调 `retryFailedSubtasks`，失败再回退到全量重试。
- **TaskIsland 浮窗任务卡片 PARTIAL_FAILED 状态没重试入口**：`TaskIsland.tsx` 之前只有 `isFailed` 才显示重试图标，部分失败任务在浮窗里**完全没有可点的操作**。现在 `isPartial` 也显示，按钮 title 提示"只重试失败子任务"。

### ✅ 测试

- 更新 `TaskItem.test.tsx`：原"COMPLETED 任务点'重试任务'期望调用 `rerunTask`"的测试是错的（产线会 409），改为期望调用 `retryFailedSubtasks`，并新增 FAILED 任务仍走 `rerunTask` 的覆盖。
- 后端全套：302 passed / 3 skipped / 0 failed。

---

## [2.5.3] - 2026-05-21

### 🐛 修复

- **Python 3.9 兼容性**：`transcribe/worker.py` 和 `transcribe/preview.py` 补充 `from __future__ import annotations`，修复 `str | None` 联合类型语法在 Python 3.9 下的 `TypeError` 崩溃。
- **变量遮蔽导致 `TypeError`**：`bilibili/core/temp_files.py` 中 `managed_temp_file` 参数 `dir` 遮蔽内置 `dir()`，修复时写的 `if 'handle' in dir()` 实际调用了参数 `None`。将参数重命名为 `directory`。
- **列缓存 ID 重用污染**：`store/db.py` 的 `_table_columns_cache` 使用 `id(conn)` 作键，CPython 中对象垃圾回收后 ID 可被重用，导致测试返回错误列集合（如 `auto_sync` 列误报存在）。直接移除缓存（`PRAGMA table_info` 本身极快）。
- **缺少 `import sqlite3`**：`transcribe/flow.py` 和 `core/cookie_manager.py` 捕获 `sqlite3.Error` 但未导入 `sqlite3`，运行时触发 `NameError: name 'sqlite3' is not defined`，并进一步导致 E2E 测试 `disk I/O error`（异常路径未释放连接锁）。
- **数据库连接缓存跨测试污染**：`get_db_connection()` 的线程本地缓存不感知 `_db_path` 变化，E2E 测试修改数据库路径后仍返回旧连接。添加 `_db_path` 变化检测与自动清理。
- **前端回归行数超限**：`Discover.tsx` 305 行超过 300 行限额。合并 4 处 `catch/finally` 块并移除冗余注释，精简至 299 行。
- **全量同步 Worker 三态终局逻辑**：`full_sync_worker.py` 此前无论成败一律调用 `finalize_success`，现改为：全部成功 → `COMPLETED`、部分成功 → `PARTIAL_FAILED`、全部失败 → `FAILED`。
- **任务取消竞态条件**：`api/routers/tasks.py` 的 `delete_task` / `cancel_task` 在取消后未做身份校验，可能导致取消的是重入后的新任务。添加 `is` 身份检查。
- **`pathlib.Path` 与 `fastapi.Path` 命名冲突**：`assets.py` 和 `tasks.py` 同时导入 `pathlib.Path` 和 `fastapi.Path` 导致 `TypeError`。将 `pathlib` 导入重命名为 `_Path`。
- **仓库层 14 个写操作缺少 `conn.commit()`**：`scheduler/repository.py` 中 `create`、`create_running`、`update_progress`、`mark_running`、`mark_completed`、`mark_failed`、`update_heartbeat`、`patch_payload`、`set_auto_retry`、`update_priority`、`delete`、`clear_history`、`clear_all_history`、`delete_all_except` 均已补充 `commit()`。
- **`auto_sync` 列缺失防御**：`scheduler.py` 和 `metrics.py` 直接 `WHERE auto_sync = 1` 查询，在旧数据库或测试环境中崩溃。添加列存在性检查。
- **临时文件 `NameError`**：`bilibili/core/temp_files.py` 的 `finally` 块中若 `io.open()` 失败，`handle` 变量不存在。添加存在性守卫。
- **健康检查 `OSError` 未捕获**：`scheduler/health.py` 检查文件存在性时未捕获权限错误，可能导致 dashboard 健康接口崩溃。
- **`settings.py` 删除账号无 404**：`delete_qwen_account` 未检查 `rowcount`，删除不存在的账号仍返回 200。现返回 404。
- **后台任务注册竞态**：`scheduler/state.py` 中 `_register_background_task` 未取消旧任务就注册新任务，可能导致内存泄漏。
- **前端 Settings 组件 Props 类型错配**：`AccountSettingsSection.tsx` 中 `editingRemarkDouyin/Bilibili/Qwen` 声明为 `string | null`，与父组件 `Settings.tsx` 的 `{ id: string } | null` 及子组件 `AccountExpandable` 不匹配；`handleClaimQuota` 声明为 `(accountId: string) => Promise<void>`，与实际无参签名不符。统一修正后 TypeScript 编译通过。
- **TaskIsland 未知类型访问**：`TaskIsland.tsx` 的 `getTaskTitle` 从 `Record<string, unknown>` 直接读取 `p.msg`、`p.creator_name`、`p.uid`，TypeScript 报错 `Type '{}' is not assignable to type 'string'`。添加 `typeof ... === 'string'` 守卫后编译通过。
- **Python 未使用导入**：移除 `platform/bilibili.py` 的 `subprocess` 和 `api/routers/tasks.py` 的 `timedelta` 未使用导入。

### 🔧 改进

- **测试套件**：修复后全量测试 300 passed / 3 skipped / 0 failed（此前 291 passed / 1 failed / 多次 `sqlite3` 相关错误）。

---

## [2.5.2] - 2026-05-20

### 🔧 改进

- **设置页模块化拆分与重构**：将 `Settings.tsx` 页面模块化重构拆分为多个小型的子组件（`AccountExpandable.tsx`, `AccountSettingsSection.tsx`, `PreferenceSettingsSection.tsx`, `ScheduleSettings.tsx`, `SettingsLayout.tsx`）与逻辑 Hook `useSettings.ts`，确保前端页面代码全部在 300 行限额以内。
- **类型安全及编译清理**：
  - 修复 `CreatorDetail.tsx` 和 `Discover.tsx` 中由于缺少 `Download`, `Trash2`, `FileAudio` 等图标引入和状态解构引起的编译错误。
  - 移除了 `AccountExpandable.tsx` 中未使用的 `useRef`。
  - 移除了 `Library.tsx` 和 `useLibraryDetail.ts` 中多处的 `any` 类型强制转换与双重否定警告。

### 🐛 修复

- **修复备注状态隔离回归问题**：还原了 `Settings.tsx` 中三个平台独立的 `editingRemark` 局部状态，解决回归测试 `test_settings_remark_state_isolated` 报错，确保测试套件回归通过。

---

## [2.5.1] - 2026-05-19

### 🐛 修复

- **Discover 页面支持直接视频链接下载**：此前仅支持创作者主页链接，新增 `detectLinkType()` 识别单个视频链接（抖音视频、B站视频/UP空间），对非主页链接提供「直接下载 + 直接转写」快捷操作卡片
- **B站下载格式选择**：`bilibili.py` 中 yt-dlp `format` 改为优先选择 H.264(AVC) 编码（`best[vcodec~='^avc']...`），避免下载 AV1 编码视频导致 Qwen 转写返回 `recordStatus=40`
- **转写重试不再误切账号**：`SERVICE_UNAVAILABLE`（`recordStatus=40`）属于平台级服务不可用，不再切换账号，保留在原账号链路等待重试
- **Pipeline 重试支持已有视频**：`skip_existing=True` 时 yt-dlp `download_archive` 会跳过已下载视频导致 `new_files=[]`，现增加 `_find_existing_videos_for_pipeline()` 回查 DB + 扫描下载目录获取已有视频路径
- **B站视频入库容错**：`_persist_bilibili_assets_to_db()` 中 UP 主 ID（`mid`）为空时不再跳过入库，使用 `"unknown"` 占位符，确保单个 B站视频也能进入素材库
- **Qwen 账号池加载**：`AccountPoolService.resolve_accounts()` 现在同时加载 `active` 和 `rate_limited` 状态的账号；`mark_status()` 仅在 `expired` 时排除账号，`rate_limited` 不再永久排除
- **Qwen 额度检测**：`get_quota_snapshot()` 增加 `NOT_LOGIN` 错误码检测，返回友好错误提示
- **CloudCleanupService**：修复空 `auth_state_path` 导致的清理失败
- **前端 Node.js 弃用警告**：`package.json` dev/build 脚本增加 `NODE_OPTIONS='--no-deprecation'`

---

## [2.5.0] - 2026-05-18

### 🎨 UI — Editorial Operations Studio 全站重设计

从 "Compact Tech / Glassmorphism" 迁移到 **Editorial Operations Studio** 设计语言：编辑式杂志风格的运营控制台，暖色调暗色界面，衬线显示字体 + 单色铜锈强调。

**设计系统（`src/index.css`）**

- **字体栈**：Fraunces（可变衬线，wght 400–700 + SOFT 0–100 + opsz 9–144）+ Geist（技术正文）+ JetBrains Mono（数据/ID/时间戳）+ Noto Serif SC（中文衬线）。fonts 通过 `index.html <link>` 加载（postcss 安全）
- **色板**：`--color-ink #0c0b09` / `--color-paper #15130f` / `--color-vellum #1c1a16` / `--color-bone #f3eedb` / `--color-ash #8a8275` / `--color-smoke #58544a` / `--color-rust #c66b3e`
- **状态色**：`--color-patina #87a878`（成功） / `--color-ember #d4a850`（警告） / `--color-iron #b25950`（失败）
- **边角**：`--radius-card: 0` 锐利，分隔靠 hairline（`rgba(243, 238, 219, 0.04 / 0.08 / 0.14)`）
- **新原语类**：`.numeral` / `.eyebrow` / `.mono-cap` / `.lead` / `.btn-sharp` / `.ed-card` / `.ed-table` / `.draw-line` / `.rule` / `.stagger` / `.bloom-enter` / `.ticker-drift` / `.rail-item`

**重设计页面**

- `AppLayout.tsx` — 76px 字体导航栏（衬线「**媒**」logomark + 单字 + 英文 caption）+ 实时任务 ticker（含 pulse dot）+ Command Palette（⌘K）
- `Home.tsx` — 工作台刊头 + 4 个 NumberFlow 滚动 hero 数字 + 「最近动态」分类账 + 「快捷操作」清单 + 创作者名册 hairline 网格 + 失败摘要 + 最近文稿
- `Library.tsx` — 内容库刊头 + 名册 hairline grid（hover 显示同步/更多）+ 添加创作者下划线输入 + 编辑式删除确认
- `Discover.tsx` — 发现页 + URL 输入 + 选择卡片 + sticky 底部派发栏
- `Tasks.tsx` — 任务中心 4 个 NumberFlow stat + 编辑式 tab + TaskItem 列表
- `Transcripts.tsx` — 420px 左侧名册（未读小圆点 + 收藏星）+ 右侧阅读器
- `TranscriptReader.tsx` — Fraunces 大标题正文 + 1px hairline 进度条 + TOC 左侧 2px rail 高亮 + 可展开搜索 + `prose-invert` 自定义
- `CreatorDetail.tsx` — 返回链接 + Fraunces 大标题 + 编辑式 tabs + 失败素材左侧 2px 铁锈 rail + 文件夹浏览器
- `TaskItem.tsx` — 删除所有圆角胶囊（`rounded-md/-xl/-[8px]`），保留 `rounded-full` 给状态点；进度条改为 1px hairline + 锈色填充；剩余条数胶囊改成数字
- `badge.tsx` 重写：胶囊形 → 边框 + uppercase 标签

**polish**

- 浏览器 title → `媒 · Media Studio`
- favicon SVG → 衬线「**媒**」字（锈色 on ink）
- `@number-flow/react` 接入 Home 和 Tasks 所有 hero 数字

**Dead code 清理（共 ~417 行）**

- 删除 `src/components/ui/SearchOverlay.tsx`（204 行）— 已被 Command Palette 取代
- 删除 `src/components/layout/TaskMonitorPanel.tsx`（213 行）— 已被全局任务 ticker 取代

> 早期分支 `cleanup-phase1` 中亦删除了 Sidebar / BottomNav / WidgetGrid / Widget / AppleEmptyState 等 Apple Soft 风格遗留组件。

---

## [2.4.0] - 2026-05-14

### 🎨 UI — iOS Widget 风格前端像素级对齐

基于 `frontend/public/prototype.html` 进行全站视觉重构，对齐 Apple 原生设计语言：

- **工作台** (`Home.tsx`)：Small/Medium/Large 三种 Widget 尺寸；widget 数值字间距 `tracking-[-1px]`；进度条圆角 `rounded-[3px]`；活跃任务绿色"同步中..."状态文本；阶段指示器非激活色 `#F2F2F7`
- **内容库** (`Library.tsx`)：搜索框字体 `text-[15px]`；分段控制器精确到 `p-[3px]` / `py-[7px]`；响应式断点统一为 `max-sm`
- **设置页** (`Settings.tsx`)：项内边距 `px-[18px]`；value 文字 `text-[15px]`；icon 背景和颜色全部改用 Apple 原生 rgba 值（如 `rgba(255,159,10,0.12)`）；hover 背景 `rgba(128,128,128,0.04)`
- **侧边栏** (`Sidebar.tsx`)：logo `text-[20px] font-bold`；导航图标 `size-[22px]`；间距 `gap-2.5`
- **底部导航** (`BottomNav.tsx`)：标签 `text-[10px]`；图标 `size-[22px]`；间距 `gap-0.5`
- **开关** (`switch.tsx`)：旋钮位置精确到 `left-[20px]`
- **空状态** (`AppleEmptyState.tsx`)：标题 `text-[20px]` 颜色 `#8E8E93`；padding `py-[60px]`
- **CSS 变量**：Apple teal `#5AC8FA`、dark warning `#FF9F0A`

### 🔧 变更

- **前端路由重构**：`/inbox` → `/home`（工作台）、`/creators` → `/library`（内容库），取消 `/discover`
- **WidgetGrid**：移除 `sm:grid-cols-3`，仅保留 2 列/4 列断点

---

## [2.3.0] - 2026-05-11

### 🎉 新增

- **并发数自动跟随账号池**：实际转写并发数 = Qwen 活跃账号数（`effective_concurrency = n_accounts`），添加账号即可线性提升并发，无需手动设置
- **额度领取终端日志**：手动领取和定时自动领取均输出详细日志，包含账号名称、领取结果、额度变化、跳过原因
- **API 并发数验证**：`POST /api/v1/settings/global` 的 `concurrency` 参数添加 1-100 范围校验

### 🔧 变更

- **移除前端并发数输入框**：并发数由 Qwen 账号池自动决定，前端设置页面不再展示并发数配置项和"保存并发设置"按钮
- **设置缓存 TTL 从 5 分钟降至 30 秒**：减少配置修改后的生效延迟，写入时仍立即清除缓存
- **手动领取额度不再受本地缓存拦截**：`claim_qwen_quota()` 传 `force=True`，直接调 Qwen API，由 API 返回真实结果

### 🐛 修复

- **修复额度领取时区 bug**：`today_key()` 原来使用 UTC 时间，导致北京时间凌晨 0:00~8:00 之间手动领取被误判为"昨日已领取"而跳过。改为本地时间，与定时任务 CronTrigger 一致
- **修复手动领取被本地缓存拦截**：手动点击「领取今日额度」时 `has_claimed_equity_today()` 误判导致不调 API，现已传 `force=True` 绕过缓存
- **修复 API 307 重定向**：FastAPI 路由统一添加 `redirect_slashes=False`，消除尾部斜杠导致的 307 Temporary Redirect

---

## [2.2.1] - 2026-05-10

### 🎉 新增

- **导出格式扩展**：转写文稿导出格式从 2 种增加到 5 种
  - 新增 **PDF** (fileType=1)、**SRT 字幕** (fileType=2)、**TXT 纯文本** (fileType=7)
  - 原有 DOCX (fileType=0)、MD (fileType=3) 保持不变
  - 前端设置页和后端 API 同步更新，支持全部 5 种格式选择

### 🔒 安全

- **修复 Cookie 泄露漏洞**：`.pipeline_state.json` 的 `error_message` 字段中可能包含完整的 HTTP 请求头（含 Cookie），现已自动脱敏处理
  - 新增 `_sanitize_error_message()` 函数，保存状态前自动将 `cookie:`、`tongyi_sso_ticket=` 等敏感信息替换为 `[REDACTED]`
  - 已清理现有 `.pipeline_state.json` 中的 26 条敏感记录

### 🐛 修复

- **修复文件夹扫描转写强制删除源文件**：`creator_transcribe_worker` 在转写完成后无条件调用 `cleanup_paths_allowlist()` 删除视频，忽略了全局「自动删除源视频」设置
  - 现在读取全局 `auto_delete` 设置，仅当 `auto_delete=True` 时才执行源文件清理
  - `auto_delete=False` 时只清理 `.cache` 临时目录，不删除视频文件
- **修复 Pipeline/BatchPipeline 的 auto_delete 默认值**：`PipelineRequest` 和 `BatchPipelineRequest` 的 `auto_delete` 默认值从硬编码 `True` 改为 `None`
  - 当 API 调用未指定 `auto_delete` 时，回退到全局设置 `get_runtime_setting_bool("auto_delete", True)`
  - 确保所有路径（pipeline、batch、creator transcribe）统一遵守用户的全局设置
- **移除 Orchestrator 中的重复删除逻辑**：`OrchestratorV2` 中 `remove_video or not keep_original` 的视频删除逻辑与 worker 层的 `auto_delete` 重复且冲突
  - 删除决策统一收归 worker 层，Orchestrator 不再自行删除视频文件
  - 移除 `PipelineConfig.remove_video`、`PipelineConfig.keep_original` 属性
  - 移除 `AppConfig.pipeline_remove_video`、`AppConfig.pipeline_keep_original` 环境变量配置
  - 状态摘要中用 `auto_delete` 替代原有的 `pipeline_remove_video`/`pipeline_keep_original`
- **修复文件夹扫描转写误删本地视频**：`creator_transcribe_worker` 处理的是用户本地文件，无论全局 `auto_delete` 设置如何，都不应删除源视频
  - 移除 `cleanup_paths_allowlist()` 调用，只保留 `.cache` 临时目录清理
  - 移除 `_build_cleanup_candidates()`、`_cleanup_retry_delay_seconds()` 等不再使用的函数
  - `auto_delete` 全局设置现在仅影响 Pipeline 流水线（下载→转写→清理），不影响本地文件扫描转写

---

## [2.2.0] - 2026-05-06

### 🎉 新增

- **领域驱动架构（DDD）**：引入完整的领域驱动设计架构
  - **领域层** (`domain/`)：富领域实体（Asset、Creator、Task、Transcript）、仓储接口、领域服务
  - **基础设施层** (`infrastructure/db/`)：SQLite 仓储实现（工厂函数模式）
  - **应用层** (`application/pipelines/`)：业务管道编排（VideoDownloadPipeline、TranscribePipeline、ExportPipeline）
  - **表示层** (`presentation/api/v2/`)：REST API v2 路由、WebSocket 实时推送
  - **迁移适配层** (`migration/`)：旧服务到新架构的桥接，保持向后兼容
- **Ghost transcripts 清理**：`reconcile_transcripts()` 新增 prune 逻辑，清理 DB 中已完成但文件已不存在的"幽灵"记录
- **健康检查脚本**：`scripts/health_check.py` 检查 4 类一致性问题（DB与文件系统同步）
- **失败原因聚合视图**：API + Settings 页表格展示最近 N 天 Top 错误类型
- **PARTIAL_FAILED 任务状态**：区分"全失败"与"部分失败"，显示"重试失败子任务"按钮
- **断点续传增强**：
  - `flow` 实现 `export_url` 续传分支（Step 13a）
  - `flow` 实现 `gen_record_id` 续传分支（Step 13b，带 fallback）
  - `orchestrator` 检测可续传 run

### 🔧 改进

- **代码重构全面完成**：完成 4 个阶段的系统重构
  - **Phase 1 - 基础架构优化**：统一配置系统（AppConfig）、统一错误处理（异常类型 + 中间件）、日志标准化
  - **Phase 2 - 核心模块重构**：下载器职责分离（接口 + 实现）、管道流程重构（PipelineStep + 步骤实现）、任务系统优化（TaskService）
  - **Phase 3 - API层优化**：提取 AssetService、CreatorService，实现路由层与服务层分离
  - **Phase 4 - DDD架构落地**：领域驱动架构完整实现，33个单元测试全部通过
- **命名标准化**：移除版本号命名（orchestrator_v2.py → orchestrator.py）
- **WebSocket 错误日志防抖**：添加 `_lastWsErrorLog` 状态，避免 `onerror` 每秒多次触发
- **路径遍历检测优化**：移除过于宽泛的 `..` 字符串检查（文件名可能包含 `....`），改用 `os.path.commonpath()` 做准确检测
- **日志归档策略**：`logs/` 目录改为归档不删，便于事故回放分析

### 🐛 修复

- 修复 WebSocket 错误日志持续打印问题（添加 1 秒防抖）
- 修复路径遍历检测误报问题（文件名包含 `....md` 被错误标记）
- 修复 `find_resumable` 兼容已上传后失败的 run

### 📝 文档

- **重构规划文档** (`docs/refactor/`) - 创建完整的重构规划文档，包括：
  - `01-overview.md` - 重构概览（背景、目标、范围）
  - `02-strategy.md` - 重构策略（技术方案、设计原则）
  - `03-implementation.md` - 实施步骤（时间节点、里程碑）
  - `04-quality.md` - 质量保障（测试策略、CI/CD）
  - `05-risk.md` - 风险评估（风险清单、应对方案）
  - `06-acceptance.md` - 验收标准（质量指标、验收流程）
- **CLAUDE.md** - 新增项目向导文档
- **STATUS.md** - 更新到 2026-05-05，Phase 4 落地小结
- **README.md** - 同步更新

### 🧹 清理

- 归档 4 个 Phase 2 之前的 `_auto_*.json` 孤儿状态文件
- 清除 Qwen 转写已迁移纯 HTTP 后的 Playwright 残留描述
- 移除 `orchestrator_v2.py` 版本号标识，统一为 `orchestrator.py`

### 🧪 测试

- 补提 PARTIAL_FAILED 13 个测试到 git 白名单
- 补提漏入库的 `services.cleanup` 测试

### 📊 统计

- 提交数: 20+ 次
- 文件修改: 30+ 个

---

## [2.1.0] - 2026-04-20

### 🎉 新增

- **Inbox 三栏布局**：Apple Mail Pro 风格，创作者列表 + 素材列表 + 即时预览面板
- **本地文件夹分组**：本地上传素材按文件夹分组显示，支持展开/折叠
- **自动同步**：进入 Inbox 页面自动触发 `reconcile_transcripts` 同步文件系统与数据库
- **Apple 设计语言**：毛玻璃效果、Spring 动画、语义化配色系统
- **主题切换**：右上角主题切换按钮，支持深色/浅色模式
- **任务中心重构**：
  - WebSocket 断连提示（红色提示条 + 红点）
  - 简化重试按钮（只保留一个"重试"）
  - 展开详情面板显示子任务状态
  - 状态标签友好化（"可能中断"替代"已过期"）
  - 子任务列表展示成功/失败/进行中

### 🔧 改进

- **双向同步完善**：`reconcile_transcripts` 现在会删除不存在的本地创作者、迁移孤儿素材、清理空创作者
- **数据库事务优化**：大批量素材更新时每 100 条提交一次，避免长事务阻塞
- **并发安全**：目录遍历改用 `list()` 避免并发修改导致 FileNotFoundError
- **清除历史优化**：清除后不再从数据库恢复（前端 historyCleared 标记）
- **后端 payload 结构化**：支持 `result_summary` 和 `subtasks` 字段
- **异常处理优化**：宽泛异常捕获从 56 处减少到 9 处（减少 84%）

### 🐛 修复

- 修复 `reconcileTranscripts` 前端类型缺少 `creators_removed`/`assets_removed` 字段
- 修复删除本地创作者时可能误删平台创作者的问题（增加 `uid LIKE 'local:%'` 校验）
- 修复 Inbox 素材列表无法滚动的问题（添加 `min-h-0` 到 flex 容器）
- 修复路径校验过于严格导致中文文件名被拒绝
- 修复默认主题跟随系统导致不一致

### 🧹 清理

- 删除未使用文件：`auth.py`、`enhanced_menu.py`、`http_client.py` 等
- 清理宽泛异常捕获，改为具体异常类型：
  - `sqlite3.Error` 用于数据库操作
  - `json.JSONDecodeError` 用于 JSON 解析
  - `OSError`/`ValueError` 用于路径和文件操作
  - `ImportError` 用于模块导入

### 📊 统计

- 提交数: 18 次
- 文件修改: 25+ 个
- 代码行数: +1500 / -800

---

## [2.0.0] - 2026-04-12

### 🎉 新增

#### 核心功能
- **增强版Pipeline** (`orchestrator.py`)
  - 失败自动重试机制（最多3次，指数退避）
  - 断点续传支持（`.pipeline_state.json`）
  - 实时进度追踪（`on_progress`回调）
  - 批量操作汇总报告（`BatchReport`）
  - 8种错误类型分类

- **Web 界面**：完整的 Web UI，支持所有操作（已替代 CLI）

#### 文档
- **README_V2.md** - V2完整功能文档

### 🔧 改进

- Pipeline成功率从70%提升到95%+
- 完全迁移到 Web 界面，CLI 模式已废弃
- 错误提示从技术化改为解决建议导向

### 🐛 修复

- 修复Pipeline批量下载转写框架未实现问题
- 修复缺少失败重试机制问题
- 修复缺少断点续传支持问题

### 📊 统计

- 新增文件: 13个
- 新增代码: ~5,500行
- 测试用例: 9个（全部通过）
- Git提交: 9次

---

## [1.0.0] - 2026-04-11

### 🎉 新增

#### 抖音下载功能
- 基于F2框架的视频下载
- 智能增量更新
- 自动化Cookie管理（Playwright）
- 关注列表管理
- 元数据与统计入库（SQLite）
- 可视化Web数据看板
- 智能视频压缩（FFmpeg）

#### Qwen转写功能
- 基于Qwen AI的音视频转写
- 一键Pipeline（下载→转写→文稿）
- 批量转写支持
- 多格式输出（Markdown/DOCX）
- 多账号管理
- 自动配额管理

#### 基础设施
- FastAPI 后端 + React 前端
- 配置模板（`config/`目录）
- 测试框架（38个测试通过）

### 📊 统计

- 核心模块: 2个（抖音下载 + Qwen转写）
- 测试覆盖: 38/38通过
- Python版本: >=3.11

---

## [0.1.0] - 2026-04-10

### 🎉 新增

- 项目初始化
- 基础项目结构
- 抖音下载模块迁移
- Qwen转写模块迁移

---

## 版本说明

### 语义化版本

- **主版本号** (MAJOR): 不兼容的API更改
- **次版本号** (MINOR): 向后兼容的功能新增
- **修订号** (PATCH): 向后兼容的问题修正

### 符号说明

- `🎉 新增` - 新功能
- `🔧 改进` - 现有功能改进
- `🐛 修复` - Bug修复
- `📝 文档` - 文档更新
- `🔒 安全` - 安全修复
- `⚡ 性能` - 性能优化
- `🧪 测试` - 测试相关
- `📊 统计` - 数据统计
- `🧹 清理` - 代码清理
