# API 契约文档 v1.0

> 本契约是前后端唯一可信数据源。任何偏离契约的实现都是 bug。

---

## 1. 通信规范

- **协议**: HTTP/1.1 + WebSocket
- **Base URL**: `http://localhost:8000/api/v1`
- **WebSocket URL**: `ws://localhost:8000/api/v1/tasks/ws`
- **Content-Type**: `application/json`
- **时间格式**: ISO 8601 (`2026-05-15T12:34:56.789012`)
- **空值**: 使用 `null`，不使用 `""` 或 `"none"`

---

## 2. 状态枚举（严格大写）

### 2.1 TranscriptStatus
```typescript
type TranscriptStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'NONE';
```

### 2.2 VideoStatus
```typescript
type VideoStatus = 'PENDING' | 'DOWNLOADING' | 'DOWNLOADED' | 'FAILED';
```

### 2.3 TaskStatus
```typescript
type TaskStatus = 'PENDING' | 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
```

### 2.4 CreatorSyncStatus
```typescript
type CreatorSyncStatus = 'ACTIVE' | 'AUTO' | 'MANUAL' | 'STALE';
```

### 2.5 Platform
```typescript
type Platform = 'douyin' | 'bilibili' | 'local';
```

**约束**: 后端数据库可存储小写，但**返回给前端的任何 JSON 必须为大写**。前后端都不做运行时转换。

---

## 3. 数据模型

### 3.1 Creator（创作者）

```typescript
interface Creator {
  uid: string;                    // 平台唯一 ID，如 "MS4wLjABAAAAxxx"
  nickname: string;               // 显示名称
  platform: Platform;             // douyin | bilibili | local
  avatar_url: string | null;      // 头像 URL
  sync_status: CreatorSyncStatus; // ACTIVE | AUTO | MANUAL | STALE
  auto_sync: boolean;             // 是否自动同步
  asset_count: number;            // 关联素材总数
  transcript_completed_count: number; // 已完成转写数量
  last_fetch_time: string | null; // 上次同步时间
  create_time: string;            // 创建时间
}
```

### 3.2 Asset（素材）

```typescript
interface Asset {
  asset_id: string;               // 全局唯一，如 "aweme:742xxx" 或 "local:sha1"
  creator_uid: string;            // 关联创作者 uid
  title: string;                  // 视频标题 / 文件名
  source_url: string | null;      // 原始链接
  source_platform: Platform;      // 来源平台
  video_path: string | null;      // 相对路径，如 "downloads/douyin/xxx.mp4"
  video_status: VideoStatus;      // PENDING | DOWNLOADING | DOWNLOADED | FAILED
  transcript_path: string | null; // 相对路径，如 "transcripts/douyin/xxx.md"
  transcript_status: TranscriptStatus; // PENDING | RUNNING | COMPLETED | FAILED | NONE
  transcript_preview: string | null; // 前 200 字摘要
  transcript_text: string | null; // 完整文本（仅详情接口返回）
  folder_path: string | null;     // 创作者子目录名，如 "douyin_博主名"
  is_read: boolean;               // 是否已读
  is_starred: boolean;            // 是否收藏
  duration: number | null;        // 视频时长（秒）
  create_time: string;            // 创建时间
  update_time: string;            // 更新时间
}
```

### 3.3 Task（任务）

```typescript
interface Task {
  task_id: string;                // UUID
  task_type: string;              // "download" | "transcribe" | "pipeline" | "batch"
  status: TaskStatus;             // PENDING | RUNNING | PAUSED | COMPLETED | FAILED | CANCELLED
  progress: number;               // 0-100
  payload: Record<string, unknown> | null; // 任务参数
  result: Record<string, unknown> | null;  // 结果摘要
  error_message: string | null;   // 失败原因
  create_time: string;            // 创建时间
  update_time: string;            // 更新时间
}
```

### 3.4 Account（转写账号）

```typescript
interface Account {
  account_id: string;             // UUID
  platform: string;               // "qwen"
  label: string;                  // 用户备注，如 "guiqing"
  status: 'ACTIVE' | 'EXPIRED' | 'RATE_LIMITED'; // 账号状态
  remaining_hours: number;        // 剩余额度（小时）
  create_time: string;
}
```

---

## 4. API 端点

### 4.1 创作者管理

#### GET /creators
**响应**: `Creator[]`

#### POST /creators
**请求**: `{ url: string }` — 创作者主页链接
**响应**: `Creator`
**错误**: 400（URL 无效）| 409（已存在）

#### DELETE /creators/{uid}
**查询参数**: `?delete_assets=true|false`（默认 false）
**响应**: `{ deleted: number, assets_deleted: number }`

#### POST /creators/{uid}/sync
**请求**: `{ mode: 'incremental' | 'full' }`
**响应**: `Task`（创建的任务）

---

### 4.2 素材管理

#### GET /assets
**查询参数**:
- `creator_uid` — 按创作者筛选
- `transcript_status` — 按转写状态筛选
- `is_starred` — 按收藏筛选
- `search` — 全文搜索关键词
- `limit` — 默认 500，最大 2000
- `offset` — 分页偏移

**响应**: `{ items: Asset[], total: number }`

#### GET /assets/{asset_id}
**响应**: `Asset`

#### GET /assets/{asset_id}/transcript
**响应**: `string`（纯文本内容，Content-Type: text/plain）

#### GET /assets/{asset_id}/file
**响应**: `Blob`（文件二进制，Content-Type 根据后缀自动判断）
**注意**: 用于浏览器直接预览，responseType 为 blob

#### DELETE /assets/{asset_id}
**响应**: `{ deleted: 1 }`

#### POST /assets/bulk-delete
**请求**: `{ ids: string[] }`
**响应**: `{ deleted: number }`

#### POST /assets/export
**请求**: `{ ids: string[], format: 'txt' | 'srt' | 'md' }`
**响应**: `Blob`（zip 包）

---

### 4.3 任务管理

#### GET /tasks
**查询参数**:
- `status` — 状态筛选
- `limit` — 默认 50

**响应**: `Task[]`

#### GET /tasks/{task_id}
**响应**: `Task`

#### POST /tasks/{task_id}/cancel
**响应**: `Task`

#### POST /tasks/{task_id}/retry
**响应**: `Task`

---

### 4.4 本地文件调度

#### POST /scan-directory
**请求**: `{ path: string }`
**响应**:
```typescript
{
  path: string;
  files: Array<{
    name: string;
    path: string;
    size: number;
    modified: number;
    suffix: string;  // "mp4" | "mp3" | "wav" | "m4a"
  }>;
}
```
**约束**: `path` 必须在用户配置的白名单目录内，禁止访问系统目录

#### POST /local-transcribe
**请求**:
```typescript
{
  files: string[];      // 绝对路径数组
  delete_after: boolean; // 转写成功后是否删除源文件
}
```
**响应**: `Task`（创建的批量转写任务）

---

### 4.5 设置

#### GET /settings
**响应**:
```typescript
{
  auto_delete: boolean;
  auto_transcribe: boolean;
  concurrency: number;
  export_format: 'txt' | 'srt' | 'md';
  accounts: Account[];
}
```

#### PATCH /settings
**请求**: 部分更新，如 `{ auto_delete: true }`
**响应**: 完整 `settings`

---

## 5. WebSocket 实时进度

### 5.1 连接
```
ws://localhost:8000/api/v1/tasks/ws
```

### 5.2 消息格式

**服务端推送**:
```typescript
interface WsMessage {
  type: 'TASK_UPDATE' | 'TASK_CREATED' | 'TASK_COMPLETED' | 'TASK_FAILED';
  task_id: string;
  status: TaskStatus;
  progress: number;      // 0-100，仅 TASK_UPDATE 有效
  payload?: Record<string, unknown>;
  timestamp: string;     // ISO 8601
}
```

**客户端心跳**（每 30 秒）:
```json
{ "type": "PING" }
```

**服务端心跳响应**:
```json
{ "type": "PONG" }
```

### 5.3 消息类型说明

| 类型 | 触发时机 | 前端行为 |
|---|---|---|
| `TASK_CREATED` | 新任务创建 | 任务列表追加 |
| `TASK_UPDATE` | 进度变化 | 更新进度条 |
| `TASK_COMPLETED` | 任务完成 | 刷新资产列表，toast 提示 |
| `TASK_FAILED` | 任务失败 | 标红，显示重试按钮 |

---

## 6. 错误响应

### 6.1 统一错误格式

```typescript
interface ApiError {
  code: string;        // 机器可读错误码，如 "ASSET_NOT_FOUND"
  message: string;     // 人类可读错误信息
  detail?: unknown;    // 额外上下文
}
```

### 6.2 HTTP 状态码映射

| 状态码 | 使用场景 | 示例 |
|---|---|---|
| 200 | 成功 | GET /assets |
| 201 | 创建成功 | POST /creators |
| 400 | 请求参数错误 | URL 格式不对 |
| 401 | 认证失败 | Cookie 过期 |
| 404 | 资源不存在 | asset_id 无效 |
| 409 | 资源冲突 | 创作者已存在 |
| 422 | 业务规则校验失败 | 超出并发限制 |
| 500 | 服务端内部错误 | 数据库连接失败 |

### 6.3 错误码清单

```typescript
type ErrorCode =
  | 'INVALID_URL'           // 创作者链接格式错误
  | 'CREATOR_EXISTS'        // 创作者已存在
  | 'CREATOR_NOT_FOUND'     // 创作者不存在
  | 'ASSET_NOT_FOUND'       // 素材不存在
  | 'TASK_NOT_FOUND'        // 任务不存在
  | 'TRANSCRIPT_NOT_FOUND'  // 转写文件不存在
  | 'PATH_NOT_ALLOWED'      // 扫描路径不在白名单
  | 'NO_AVAILABLE_ACCOUNT'  // 无可用的 Qwen 账号
  | 'QUOTA_EXHAUSTED'       // 额度用尽
  | 'INTERNAL_ERROR';       // 内部错误
```

---

## 7. 文件路径规范

### 7.1 存储结构

```
project_root/
  data/
    downloads/           # 下载的视频
      {platform}/
        {creator_folder}/
          {video_file}
    transcripts/         # 转写结果
      {creator_folder}/
        {transcript_file}
    media_tools.db       # SQLite 数据库
```

### 7.2 路径规则

- 数据库存储**相对路径**（相对于 `data/`）
- API 返回的也是相对路径
- 前端需要完整 URL 时，拼接 `API_BASE_URL + '/assets/{asset_id}/file'`
- **禁止**前后端各自拼接路径，统一由后端 `getAssetFileUrl` 服务生成

---

## 8. 约束红线

### 8.1 后端红线
1. 返回给前端的任何状态字符串必须大写
2. `UPDATE media_assets` 必须有 `WHERE asset_id = ?`，禁止模糊匹配
3. `transcript_path` 写入前必须先 `SELECT` 确认目标 asset 存在
4. 文件路径解析统一使用 `get_transcripts_path()` / `get_download_path()`，禁止硬编码

### 8.2 前端红线
1. 不对后端返回的数据做大小写转换
2. 不直接拼接文件路径，统一调用 `getAssetFileUrl(asset_id)`
3. 任何状态判断使用契约中的枚举值，不使用魔法字符串
4. 阅读器组件必须内联渲染，禁止 `window.open` 或下载后打开

---

## 9. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-05-15 | 初始版本 |
