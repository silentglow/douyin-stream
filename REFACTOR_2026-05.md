# REFACTOR 2026-05 — 验收契约

> 这是一份**执行期契约**，不是设计文档。每个任务有 5 个必经字段，**少一个都不能算完成**：起点状态 / 终点状态 / 回归测试 / 同步文档 / 副作用清单。
>
> 起点状态写明"问题存在"的可执行命令；终点状态同一组命令必须给出相反结果。
>
> 完成后此文件归档到 `docs/refactor/2026-05.md` 或删除——**不是长期文档**。

## 反模式与防御

| 反模式 | 防御 |
|---|---|
| "改了文件就算完成" | 任务用**状态**描述（grep 返回什么），不是动作 |
| 测试绿了 = 没问题 | 每任务必加**会失败 → 修复后才通过**的回归测试 |
| 改完忘了同步文档 | 任务清单显式列同步项，文档没改 = 任务未完 |
| 跨任务"顺手做" | 每任务严守 scope，发现额外问题 → 单独 issue，不扩大 |
| commit 多任务 | 每任务一 commit，便于 revert |

---

## 任务 1 — 清空目录 + db.core shim + 孤儿文件（0.5 天）

### 起点状态（已验证）

```bash
$ find src/media_tools/pipeline src/media_tools/repositories -type f
# 0 files but dirs exist

$ ls src/media_tools/db/core.py
# exists; grep 显示有 1 处引用

$ ls -d src/data src/logs src/media_tools/downloads
# 三处历史残骸目录都还在

$ ls src/logs/ | head
# 还残留 60+ 个 f2-* 日志文件 (4 月之前的)

$ ls douyin_users.db src/data/media_tools.db src/media_tools/douyin_users.db
# 三处分散的 sqlite 文件，新机器跑起来不知道哪个真
```

### 终点状态

```bash
$ ls src/media_tools/pipeline 2>&1 | grep -q "No such" ; echo $?
0
$ ls src/media_tools/repositories 2>&1 | grep -q "No such" ; echo $?
0
$ test ! -f src/media_tools/db/core.py ; echo $?
0
$ grep -rn "from media_tools.db.core\|from .db.core" src/ --include="*.py" | grep -v __pycache__
# 空输出

$ ls -d src/data src/logs src/media_tools/downloads 2>&1 | grep -c "No such"
3

$ ls src/media_tools/douyin_users.db douyin_users.db 2>&1 | grep -c "No such"
2  # data/douyin_users.db 是唯一正本
```

### 回归测试

启动后端，跑全量 pytest，应 302+ passed（不降）。

`.venv/bin/python -c "import media_tools; from media_tools.api.app import app"` 退出码 0。

### 同步文档

- `CLAUDE.md`：移除任何提到 pipeline/repositories 的目录列表
- `.gitignore`：确认 `src/data/`、`src/logs/`、`src/media_tools/downloads/` 已被忽略；不在则补
- `CHANGELOG.md`：在 "Unreleased" 段加一行

### 副作用清单

- 删除 db/core.py 前必须把唯一的 1 处引用迁到 store/db
- 清 `.pyc` 缓存后再跑测试（`find . -name __pycache__ -exec rm -rf {} +`）
- 删的 db 文件如果含真实数据要确认 data/douyin_users.db 是同款最新；如果数据更新只在老路径里，先 merge
- 删 src/logs/ 时不要误删 data/logs/（真正在用的日志）

---

## 任务 2 — transcribe 三个 error 模块合一（0.5 天）

### 起点状态（已验证）

```bash
$ ls src/media_tools/transcribe/error*.py | wc -l
3   # errors.py (21) + error_types.py (60) + error_classifier.py (111)

$ grep -rn "from media_tools.transcribe.error_types\|error_classifier" src/ --include="*.py" | grep -v __pycache__ | wc -l
# 应有 >0 处引用旧路径
```

### 终点状态

```bash
$ ls src/media_tools/transcribe/error*.py | wc -l
1   # 只剩 errors.py

$ grep -rn "from media_tools.transcribe.error_types\|from media_tools.transcribe.error_classifier" src/ --include="*.py" | grep -v __pycache__
# 空输出

# 新 errors.py 必须同时含异常类 + 类型 enum + classify 函数
$ .venv/bin/python -c "from media_tools.transcribe.errors import TranscribeError, ErrorType, classify_error; print('OK')"
OK
```

### 回归测试

- `tests/test_error_types.py` 现有测试仍通过
- **新增** `tests/test_error_module_consolidation.py`：
  - 枚举旧两个模块的 public API（>=12 个名字）能从新 errors 模块 import
  - `import media_tools.transcribe.error_types` 必须 `ImportError`
  - `import media_tools.transcribe.error_classifier` 必须 `ImportError`

### 同步文档

- `CHANGELOG.md` 记录合并 + 列出迁移的 API
- 任何引用旧路径的文档/注释一并改

### 副作用清单

- 前端 `services/tasks.ts` 是否 hardcode 旧 error_type 字符串？grep 确认
- error_classifier 里的"建议文案"是否被某 UI 直接调用？grep 确认
- 旧 import 路径必须真死透——别留 `from .error_types import * as _legacy` 这种偷工

---

## 任务 3 — API 字段 snake_case 单边发车（2 天）

**最容易被偷工减料，验收最严。**

### 起点状态（已验证）

```bash
$ curl -s http://127.0.0.1:8000/api/v1/settings/qwen/accounts/status | python3 -c "
import json, sys, re
data = json.load(sys.stdin)
keys = re.findall(r'\"([a-z]+[A-Z][a-zA-Z]*)\"', json.dumps(data))
print(set(keys))
"
# 至少应命中 accountId / accountLabel

$ grep -rn "accountId\|accountLabel" frontend/src/ --include="*.ts" --include="*.tsx" | grep -v "@deprecated" | wc -l
# >0 处仍在用
```

### 终点状态

```bash
# 新增的 contract test 通过
$ .venv/bin/python -m pytest tests/api/test_no_camelcase_in_responses.py -v
# 全过

# 前端无 camelCase 业务字段引用
$ grep -rn "accountId\|accountLabel" frontend/src/ --include="*.ts" --include="*.tsx" | grep -v "@deprecated"
# 空输出（@deprecated 注释允许保留作为迁移记录但代码逻辑不能引用）
```

### 回归测试（新增 contract test）

`tests/api/test_no_camelcase_in_responses.py`：

```python
"""枚举所有 GET 路由，递归扫 JSON keys，
断言所有 key 都是 snake_case（或非字母如 status_code）。
commit 前红（accounts/status 命中 accountId），改完绿。"""
```

实现要点：用 fastapi TestClient 遍历 `app.routes`，对每个 GET 路由发请求，递归走 response JSON，找到 `re.match(r'^[a-z]+[A-Z]', key)` 的 key 立刻 assert fail 并打印路径。

### 同步文档

- `frontend/src/types/index.ts` 删 `@deprecated` 字段（保留**注释**说明历史）
- 后端 dual emit 的 camelCase 字段全删
- `docs/references/api.md`（如有）字段名同步

### 副作用清单

- `useSettings.ts` 的 `a.account_id || a.accountId` fallback——本次**保留 fallback 一个 PR**，下个 PR 再删；commit message 必须说明这一点
- `dashboard.ts`、`Home.tsx` 的 inline 类型同步删 camelCase
- 后端 `accounts/status.py` 的 `accounts/{id}/status` `claim_qwen_quota` 两处 dual emit 同步删
- 必须**重启 uvicorn**让 reload 真正生效后再跑 contract test

---

## 任务 4 — 配置 5 层压到 2 层（2 天）

### 起点状态（已验证）

```bash
$ grep -rn "os\.environ\.get" src/media_tools/ --include="*.py" 2>/dev/null | grep -v __pycache__ | wc -l
23

$ grep -n "_settings_cache_ttl" src/media_tools/core/config.py
48:_settings_cache_ttl: int = 300  # 5 分钟
```

历史问题：`export_format=pdf` 类设置改 DB 后 5 分钟内后端拿不到新值。

### 终点状态

```bash
# os.environ.get 只在启动路径上调用
$ grep -rn "os\.environ\.get" src/media_tools/ --include="*.py" 2>/dev/null | grep -v __pycache__ | grep -vE "(config\.py|app\.py|/transcribe/config\.py|main\.py)" | wc -l
0   # 或一个明确的允许列表，写在 docs/architecture/config.md

# 缓存 TTL
$ grep -n "_settings_cache_ttl" src/media_tools/core/config.py
*** _settings_cache_ttl: int = 5

# 架构文档明确两层
$ test -f docs/architecture/config.md ; echo $?
0
```

### 回归测试（新增）

`tests/test_config_layers.py`：

```python
"""1. 启动后从 DB 改一个 setting，wait 6s（>cache TTL），断言
   AppConfig.get() 拿到新值，不需要重启。
2. import 时 grep src/ 里的 os.environ.get 直接调用次数 ≤ 白名单数（防回滚）。"""
```

并新增 **e2e 防回归**：`tests/test_export_format_changes_take_effect.py`：

```python
"""模拟 export_format 从 pdf 改为 md：
DB 设 export_format=pdf → 转写一个 fake file 应得 .pdf 名
DB 改 export_format=md → wait 6s → 转写一个 fake file 应得 .md 名"""
```

### 同步文档

- **新增** `docs/architecture/config.md`，明确：
  - Layer 1：`config/config.yaml` + `.env`（仅 startup 一次性加载）
  - Layer 2：`SystemSettings` DB 表（运行期 mutable）
  - 禁止散落 `os.environ.get`，统一走 `AppConfig.get(...)`
- `CHANGELOG.md` 记录 TTL 改动 + 散落 env 收敛
- `.env.example` 删已经无效的项

### 副作用清单

- TTL 改 5 秒会增加 DB 读次数（每秒最多 1 次），**可接受**
- 必须**重启 uvicorn** 让新 TTL 生效，再跑 e2e 测试
- 历史 export_format 这个具体设置必须有 e2e test，**不允许只靠 TTL 缩短了事**

---

## 任务 5 — 验收日（不写新代码，半天到一天）

### 执行步骤

```bash
# 1. 全量后端测试
.venv/bin/python -m pytest tests/ -v --tb=short

# 2. 全量前端测试
cd frontend && npx vitest run

# 3. 4 条新回归测试单独跑确认
.venv/bin/python -m pytest \
  tests/test_error_module_consolidation.py \
  tests/api/test_no_camelcase_in_responses.py \
  tests/test_config_layers.py \
  tests/test_export_format_changes_take_effect.py -v

# 4. 起点命令再跑一遍，必须返回"问题已消失"（对照每个任务的起点）

# 5. 前端 production build
cd frontend && npx vite build

# 6. 后端启动 + 健康检查
./run.sh backend &
sleep 5
curl -fsS http://127.0.0.1:8000/api/health

# 7. 手测
#    a. 起一个 local_transcribe 任务 → island 显示每文件成功/失败
#    b. 点单条删除任务 → 任务从 island 消失
#    c. 改 settings.export_format pdf→md → 5 秒后新转写产物是 .md
#    d. PDF 转录稿在 TranscriptReader 里能看到
```

### 验收通过条件

- 上面 6 个命令全部退出码 0
- 手测 4 个路径全部丝滑
- 没有"我以为修了但其实没"的兜底惊喜

### 失败处理

任何一步红：不 push，原地 debug。**禁止"差不多就 push"。**

---

## 执行守则（重复一遍以免忘）

1. **每任务一 commit**。commit message 必须含起点 + 终点 + 测试 + 文档同步清单
2. **遇到契约外的问题先停下问**，不擅自扩大 scope
3. **不删现有 passing test**（除非测试对应的代码删了）
4. **改完不跑测试不 commit**
5. **同步文档没改 = 任务未完**
