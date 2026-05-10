# 常见问题解答 (FAQ)

在使用抖音批量下载工具的过程中，您可能会遇到一些常见问题，以下是相关排查及解决方案。

## 🔑 Cookie 与登录相关

### Q1: 下载时提示 `未配置 cookie，请在 config/config.yaml 中设置`
- **原因**：由于未登录或配置的 Cookie 无效，导致请求被抖音服务器拦截。
- **解决方案**：
  请运行 `python scripts/login.py` 唤起扫码登录界面，用抖音 App 扫码登录。登录成功后，脚本会自动将最新 Cookie 写入 `config/config.yaml` 中。

### Q2: 为什么提示 Cookie 已过期？
- **原因**：抖音的身份认证具有时效性。长时间不活动或异地登录会导致原 Cookie 失效。
- **解决方案**：重新运行 `python scripts/login.py` 扫码更新即可。

## ⚙️ 环境与依赖问题

### Q3: 运行 `compress.py` 报错 `未找到 ffmpeg`
- **原因**：您的系统中没有安装 `ffmpeg` 或未配置系统环境变量。
- **解决方案**：
  - macOS: `brew install ffmpeg`
  - Ubuntu: `sudo apt install ffmpeg`
  - Windows: 建议使用 `choco install ffmpeg` 或手动下载后配置 Path 环境变量。

## 📥 下载与数据相关

### Q4: 为什么有些视频没有被下载？
- **原因**：
  1. 脚本默认开启了**增量更新**。若本地已存在相同 `aweme_id` 的视频，则会自动跳过。
  2. 该视频可能被作者设置为私密或已被删除。
  3. 你的请求过于频繁，触发了临时风控。
- **排查建议**：您可以尝试在浏览器中打开对应博主主页，确认视频是否正常可见。如被风控，建议等待几个小时后再试。

### Q5: 为什么打开 Web 界面 (`index.html`) 数据没有更新？
- **原因**：Web 界面依赖 `data.js` 文件中的静态数据，下载完成后需要重新生成它。
- **解决方案**：
  在终端中运行 `python scripts/generate-data.py`。命令执行成功后，刷新浏览器页面即可看到最新数据。

### Q6: 为什么视频压缩后大小反而变大了？
- **原因**：如果原始视频体积过小，重新编码的头部开销可能会大于压缩收益。
- **解决方案**：工具默认会跳过小于 5MB 的文件。如果仍想强制跳过压缩，建议加上 `--no-skip-small` 并使用更低画质参数 `--crf 38` 或使用 `--aggressive` 模式。

## 🔒 安全与隐私

### Q7: Cookie 等敏感信息会被记录到日志或状态文件中吗？
- **不会**。从 v2.2.1 起，所有写入 `.pipeline_state.json` 的错误信息都会经过自动脱敏处理，`cookie`、`tongyi_sso_ticket` 等敏感字段会被替换为 `[REDACTED]`，不会明文存储。

### Q8: Cookie 存储在哪里？
- Cookie 存储在以下位置（按实际调用优先级排列）：
  - **多账号模式**（Settings 页添加的 Qwen 账号）：存储在 SQLite 数据库 `Accounts_Pool` 表的 `cookie_data` 字段中
  - **单账号模式**（默认认证）：优先从 SQLite 数据库 `auth_credentials` 表的 `auth_data` 字段读取；若 DB 为空则回退到文件 `.auth/qwen-storage-state.json`
  - 环境变量 `QWEN_COOKIE_STRING` 仅用于测试场景，不建议在生产环境中使用
- 抖音/B站 Cookie 存储在 SQLite 数据库 `Accounts_Pool` 表中

## 📄 导出与转写

### Q9: 支持哪些导出格式？
- 目前支持 5 种格式：
  - **MD**（Markdown）— 默认格式，适合阅读和编辑
  - **DOCX**（Word 文档）— 适合正式文档场景
  - **PDF** — 适合分享和归档
  - **SRT**（字幕文件）— 适合视频字幕制作
  - **TXT**（纯文本）— 适合最简输出
- 可在 Settings 页面的「导出格式」选项中切换

### Q10: 关闭「自动删除源视频」后，转写还会删除我的视频吗？
- **不会**。从 v2.2.1 起，「自动删除源视频」设置仅影响 Pipeline 流水线（下载→转写→清理）中下载的视频。
- **本地文件扫描转写**（creator transcribe）永远不会删除用户的源视频文件，无论全局设置如何，只清理 `.cache` 临时目录。