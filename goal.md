# 剩余重构任务

## Phase 3: Workers 与 Pipeline 拆分

### Task 12b: transcribe/ 吞并 pipeline/ 核心
- [ ] git mv pipeline/orchestrator.py → transcribe/service.py
- [ ] git mv pipeline/models.py → transcribe/models.py
- [ ] git mv pipeline/error_types.py → transcribe/error_types.py
- [ ] git mv pipeline/helpers.py → transcribe/helpers.py
- [ ] git mv pipeline/config.py → transcribe/config.py
- [ ] git mv pipeline/preview.py → transcribe/preview.py
- [ ] git mv pipeline/preview_backfill.py → transcribe/preview_backfill.py
- [ ] 更新所有跨模块 import
- [ ] 跑测试验证

### Task 13: download/ 域
- [ ] 创建 download/__init__.py
- [ ] 从 pipeline_worker.py 提取 DownloadWorker → download/worker.py
- [ ] 从 pipeline/download_router.py 提取调度逻辑 → download/service.py

### Task 14: creators/ 域
- [ ] 创建 creators/__init__.py
- [ ] git mv repositories/creator_repository.py → creators/repository.py
- [ ] git mv workers/creator_sync.py → creators/sync.py
- [ ] 合并 services/ 中创作者相关业务逻辑 → creators/service.py
- [ ] 更新 import

## Phase 4: 平台模块合并

### Task 15: platform/ 合并 douyin/ + bilibili/
- [ ] 创建 platform/__init__.py, platform/base.py
- [ ] 合并 douyin/core/ 核心逻辑 → platform/douyin.py
- [ ] 合并 bilibili/core/ 核心逻辑 → platform/bilibili.py
- [ ] 更新 api/routers/douyin.py 等路由 import
- [ ] 跑测试验证

## Phase 5: API 路由整理

### Task 16: API 路由瘦身
- [ ] 清理 api/routers/ 中过时的路由
- [ ] 统一错误响应格式
- [ ] 跑测试验证

## Phase 6: 配置/日志/测试/清理

### Task 17: 配置统一
- [ ] 所有配置集中到 config/
- [ ] 删除散落在各模块的 config 文件

### Task 18: 日志统一
- [ ] 所有日志集中到 logs/
- [ ] 删除空日志文件

### Task 19: 测试清理
- [ ] 删除废弃测试
- [ ] 修复 import 路径
- [ ] 全量测试通过

### Task 20: 最终清理
- [ ] 删除空目录
- [ ] 删除未引用文件
- [ ] 验证无 import error
- [ ] 全量测试通过
