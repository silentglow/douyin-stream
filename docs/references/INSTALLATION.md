# 安装指南 (Installation Guide)

本技能依赖特定环境与 Python 库。请按照以下说明依次完成环境配置。

## 1. 环境自检工具 (推荐)
本项目内置了环境自检脚本，可以帮助你一键确认当前环境是否满足要求：
```bash
python scripts/check_env.py
```
若检查未通过，请继续阅读下方的详细安装步骤。

## 2. 系统依赖

### Python 版本
要求：**Python 3.9 - 3.13** (由于底层 `f2` 库的限制)。

### FFmpeg (视频压缩功能所需)
**可选**：如果您不需要使用 `scripts/compress.py` 压缩视频功能，则可跳过此步骤。

| 操作系统 | 安装命令 / 下载方式 |
| :--- | :--- |
| **macOS** | `brew install ffmpeg` |
| **Ubuntu/Debian** | `sudo apt install ffmpeg` |
| **Windows** | `choco install ffmpeg` 或从 [FFmpeg 官网](https://ffmpeg.org/download.html) 下载并配置环境变量 |

## 3. Python 依赖包

本项目依赖如下核心包：
| 包名 | 用途 |
| :--- | :--- |
| `f2` | 抖音视频下载核心框架 |
| `pyyaml` | YAML 配置文件解析 |
| `httpx` | 异步 HTTP 客户端 |
| `aiofiles` | 异步文件操作 |

### 安装命令

安装 Python 依赖库：
```bash
pip install f2 pyyaml httpx aiofiles
```
> **注意**：如果上述命令因网络问题失败，请尝试设置相应的镜像源，或多试几次。

## 4. 初始化配置文件

安装完所有依赖后，初始化你的个人配置：

```bash
# 复制模板文件
cp config/config.yaml.example config/config.yaml
```

## 5. 数据目录说明

项目所有运行时数据统一存储在 `data/` 目录下：

| 目录 | 用途 |
| :--- | :--- |
| `data/` | 运行时数据根目录 |
| `data/media_tools.db` | SQLite 数据库文件 |
| `data/auth/` | 认证状态文件（Qwen storage state、账号池状态等） |
| `data/downloads/` | 下载的视频文件 |
| `data/transcripts/` | 转写文本文件 |
| `data/logs/` | 日志文件 |

配置模板存放在 `config/` 目录下：

| 文件 | 用途 |
| :--- | :--- |
| `config/config.yaml.example` | 主配置模板（复制为 `config.yaml` 使用） |
| `config/auth_rules.yaml` | Cookie 验证规则 |
| `config/transcribe/.env.example` | Qwen 转写环境变量模板 |

数据库路径和下载路径可通过 `config/config.yaml` 配置：

```yaml
database:
  path: data/media_tools.db

download:
  path: data/downloads
```

> **注意**：旧版本中散落在项目根目录的 `.auth/`、`downloads/`、`logs/`、`transcripts/` 目录已迁移到 `data/` 下。启动时系统会自动迁移旧路径的文件。