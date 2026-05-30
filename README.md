# Media Tools

> 视频素材抓取 → 云端转写 → 本地阅读，一站式内容工作台。

![React](https://img.shields.io/badge/Frontend-React%2019-61DAFB?logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11%2B-brightgreen?logo=python&logoColor=white)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Media Tools 是一个本地化的 Web 工作台，帮助你从抖音/B站批量抓取视频、通过通义千问云端转写为文字稿，并在浏览器中沉浸式阅读和管理。前后端分离架构，**Editorial Operations** 设计语言（暖色调暗色界面、Fraunces 衬线显示字体、单色铜锈强调色），以编辑式的克制呈现高密度运营数据。

---

## 核心特性

### Creators — 创作者管理

- 添加抖音/B站博主，自动拉取头像、简介等信息
- 支持增量同步和全量重拉两种模式
- 定时自动同步（APScheduler cron 表达式）
- 一键删除创作者及其所有关联视频、文稿和数据库记录

### Discover — 发现与选取

- 输入博主主页链接，极速预览视频列表（含封面、时长、标题）
- 勾选感兴趣的视频后选择「仅下载」或「下载 + 转写」
- 本地文件转写：选择本地音视频文件，跳过下载直接转写
- 告别盲盒式全量下载，按需处理

### Settings — 全局配置

- 抖音/B站 Cookie 池管理，动态添加/移除账号
- 通义千问认证配置（支持多账号轮换）
- 全局开关：并发数、转写后自动删除源视频、下载后自动触发转写
- 导出格式选择：MD、DOCX、PDF、SRT、TXT 五种格式

### 任务系统

- 后台异步执行，WebSocket 实时推送进度到前端（含心跳保活）
- 任务取消 / 重试 / 断点续跑
- 失败自动重试（指数退避）+ 错误分类
- 三态任务结果：`COMPLETED` / `PARTIAL_FAILED`（部分子任务失败）/ `FAILED`，前端 badge 区分显示
- **可恢复转写流水线**：Qwen 上传后任意环节失败，下次重试从 `gen_record_id` 续做；长转写轮询超时只保留远端记录等待下次续传，不重传文件、不重复消耗配额
- 子任务详情：展示每个视频的成功/失败状态，支持"只重试失败子任务"
- 全局任务监控面板 + Settings 页失败原因聚合视图（最近 N 天 Top 错误类型）
- 健康检查脚本：`python scripts/health_check.py` 扫描 DB 与文件系统一致性问题

### UI 设计语言

- **Editorial Operations Studio**：暖色近黑底（`#0c0b09`）+ 奶白文字（`#f3eedb`）+ 单一氧化铜锈色强调（`#c66b3e`）
- 字体栈：**Fraunces**（衬线显示，可变字重 + SOFT 轴）+ **Geist**（技术正文）+ **JetBrains Mono**（数据、ID、时间戳）+ **Noto Serif SC**（中文衬线）
- 锐利边角（`--radius-card: 0`）、毛细分隔线、`@number-flow/react` 数字滚动动画
- 仅暗色，不切换主题；logomark 为衬线「**媒**」字

---

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 19 + Vite + TypeScript + Tailwind CSS v4 + shadcn/ui + Zustand + Framer Motion + @number-flow/react |
| 后端 | Python 3.11+ + FastAPI + SQLite (WAL) + APScheduler |
| 核心 | f2（抖音）、yt-dlp（B站）、Qwen HTTP API（云端转写）、FFmpeg（音视频处理） |

---

## 快速启动

### 环境要求

- **Python 3.11+**
- **Node.js 18+**（含 npm）
- **FFmpeg**（音视频处理）

### 获取代码

```bash
git clone https://github.com/guiqingjob/douyin-stream.git
cd douyin-stream
```

### 一键启动

```bash
chmod +x run.sh   # 仅首次
./run.sh           # 同时启动后端 (8000) 和前端 (5173)
```

启动成功后访问 `http://localhost:5173`。

### 分步启动

```bash
./run.sh backend    # 仅启动 FastAPI 后端
./run.sh frontend   # 仅启动 React 开发服务器
./run.sh build      # 编译前端生产环境产物到 frontend/dist/
```

脚本会自动检测并安装缺失的 Python / npm 依赖。

---

##### 配置说明

首次启动时从 `config/config.yaml` 读取基础配置（Cookie、下载路径等），运行时配置（自动转写、导出格式等）存储在 SQLite 数据库中，通过 Settings 页面可视化管理，主要字段：

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `cookie` | 抖音登录 Cookie | 通过 Settings 页面配置 |
| `download_path` | 视频下载存储路径 | `data/downloads` |
| `auto_transcribe` | 下载后自动触发转写 | `false` |
| `auto_delete_video` | 转写成功后删除源视频 | `true` |
| `export_format` | 转写文稿导出格式 | `md` |
| `naming` | 视频文件命名模板 | `{desc}_{aweme_id}` |

部署级 Qwen 转写环境变量：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `QWEN_TRANSCRIBE_POLL_TIMEOUT_SECONDS` | 单次等待 Qwen 转写完成的最长轮询时间；超时不代表远端失败，系统会保留 `record_id/gen_record_id` 供下次续传 | `21600` |

> **导出格式**：支持 `md`（Markdown）、`docx`（Word 文档）、`pdf`（PDF 文档）、`srt`（字幕文件）、`txt`（纯文本）五种格式，可在 Settings 页面切换。

> **自动删除源视频**：此设置仅影响 Pipeline 流水线（下载→转写→清理）中下载的视频。本地文件扫描转写永远不会删除用户源视频，只清理临时文件。

通义千问认证状态统一存储在 SQLite 数据库 `Accounts_Pool` 表中，通过 `CookieManager` 统一接口管理，支持三平台（抖音/B站/Qwen）账号轮换。运行时缓存在 `data/auth/` 目录下。通过 Settings 页面配置。

---

## 项目结构

```
media-tools/
├── frontend/                  # React SPA（已纳入主仓库）
├── src/media_tools/
│   ├── api/                   # FastAPI 应用
│   │   ├── routers/           # 路由：creators, assets, tasks, settings, douyin, scheduler 等
│   │   └── websocket_manager.py  # WebSocket 任务推送 + 心跳
│   ├── accounts/              # Qwen 账号池与额度管理
│   ├── assets/                # 媒体资产读写、GC、文件操作
│   ├── bilibili/              # B站集成：下载、UP主管理
│   ├── common/                # HTTP 客户端、运行时工具等共享基础
│   ├── core/                  # 统一配置系统 + CookieManager + 安全存储
│   ├── creators/              # 创作者同步流水线
│   ├── douyin/                # 抖音集成：下载、关注管理、Cookie 认证
│   ├── download/              # 下载器统一抽象
│   ├── platform/              # 平台无关的浏览器/系统适配
│   ├── scheduler/             # APScheduler 定时任务（账号轮询、自动同步等）
│   ├── services/              # 业务逻辑层：任务操作、文件浏览、Qwen 状态等
│   ├── store/                 # SQLite 数据库初始化、FTS5 索引、路径工具
│   ├── transcribe/            # 通义千问转写流水线：编排、OSS 上传、轮询、导出、断点续传、进度调度
│   └── workers/               # 后台任务 worker（调度器注册入口）
├── config/                    # 配置模板和规则文件
├── data/                      # 运行时数据（数据库、认证、下载、日志）
│   ├── media_tools.db         # SQLite 数据库
│   ├── auth/                  # 认证状态缓存
│   ├── downloads/             # 视频下载目录
│   ├── transcripts/           # 转写文稿输出目录
│   └── logs/                  # 日志文件
├── deploy/                    # Dockerfile / docker-compose 部署配置
├── scripts/                   # 启动与运维脚本（start.sh、health_check.py 等）
├── tests/                     # 测试套件（按模块分目录镜像 src/）
└── run.sh                     # 一键启动入口（转发到 scripts/start.sh）
```

---

## 开源协议

[MIT License](LICENSE)
