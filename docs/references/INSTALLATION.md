# 安装指南 (Installation Guide)

本指南帮助你完成环境配置和项目安装。

## 1. 系统依赖

### Python 版本
要求：**Python 3.11+**（项目使用 pyproject.toml 管理依赖，需要 3.11 及以上版本）。

### FFmpeg（转写功能所需）
**可选**：如果不需要视频转写功能，可跳过此步骤。

| 操作系统 | 安装命令 / 下载方式 |
| :--- | :--- |
| **macOS** | `brew install ffmpeg` |
| **Ubuntu/Debian** | `sudo apt install ffmpeg` |
| **Windows** | `choco install ffmpeg` 或从 [FFmpeg 官网](https://ffmpeg.org/download.html) 下载并配置环境变量 |

## 2. 安装项目

```bash
# 克隆项目
git clone <repo-url>
cd media-tools

# 安装项目及所有依赖
pip install -e .

# 如需开发依赖（测试、lint 等）
pip install -e ".[dev]"
```

## 3. 初始化配置文件

安装完所有依赖后，初始化你的个人配置：

```bash
# 复制模板文件
cp config/config.yaml.example config/config.yaml
```

## 4. 启动服务

```bash
# 启动后端 API 服务
python -m media_tools.api.app

# 启动前端开发服务器（另一个终端）
cd frontend && npm install && npm run dev
```

启动后在浏览器打开前端页面，通过 **Settings** 页面完成 Cookie 配置和账号添加。

## 5. 数据目录说明

项目所有运行时数据统一存储在 `data/` 目录下：

| 目录 | 用途 |
| :--- | :--- |
| `data/` | 运行时数据根目录 |
| `data/media_tools.db` | SQLite 数据库文件 |
| `data/auth/` | 认证状态文件（Qwen 认证状态、账号池状态等） |
| `data/auth/quota-usage.json` | Qwen 额度领取记录（按账号+日期组织） |
| `data/downloads/` | 下载的视频文件 |
| `data/transcripts/` | 转写文本文件 |
| `data/logs/` | 日志文件 |

配置模板存放在 `config/` 目录下：

| 文件 | 用途 |
| :--- | :--- |
| `config/config.yaml.example` | 主配置模板（复制为 `config.yaml` 使用） |
| `config/auth_rules.yaml` | Cookie 验证规则 |

> **注意**：旧版本中散落在项目根目录的 `.auth/`、`downloads/`、`logs/`、`transcripts/` 目录已迁移到 `data/` 下。启动时系统会自动迁移旧路径的文件。
