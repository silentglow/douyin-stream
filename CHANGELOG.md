# 变更日志

所有重要更改都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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
