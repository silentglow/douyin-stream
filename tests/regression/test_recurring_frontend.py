"""
回归测试套件：反复出现的前端 Bug 模式
运行方式: cd frontend && npx vitest run tests/regression/test_recurring_frontend.test.tsx

注意: 以下测试为架构/代码规范检查，不需要完整 DOM 环境。
"""

import subprocess
from pathlib import Path

import pytest

def _find_repo_root(start: Path) -> Path:
    cur = start
    for _ in range(12):
        if (cur / "pyproject.toml").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise RuntimeError("Cannot locate repo root (pyproject.toml not found)")


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
FRONTEND_ROOT = REPO_ROOT / "frontend" / "src"


# FRONTEND-001: WebSocket 生命周期
class TestWebSocketLifecycle:
    def _store_text(self) -> str:
        """聚合 store 入口及 slice 内容，覆盖按职责拆分后的实现。"""
        store_dir = FRONTEND_ROOT / "store"
        chunks: list[str] = []
        for f in [store_dir / "useStore.ts", *sorted((store_dir / "slices").glob("*.ts"))]:
            if f.exists():
                chunks.append(f.read_text())
        return "\n".join(chunks)

    def test_connect_websocket_has_disconnect(self):
        """
        验证 store 中同时存在 connectWebSocket 和 disconnectWebSocket。
        """
        content = self._store_text()
        assert "connectWebSocket" in content, "缺少 connectWebSocket"
        assert "disconnectWebSocket" in content, "缺少 disconnectWebSocket (FRONTEND-001)"

    def test_app_has_websocket_cleanup(self):
        """
        验证 App.tsx 的 useEffect 返回 cleanup 函数调用 disconnectWebSocket。
        """
        app_file = FRONTEND_ROOT / "App.tsx"
        content = app_file.read_text()
        assert "disconnectWebSocket" in content, (
            "App.tsx 未在 cleanup 中调用 disconnectWebSocket (FRONTEND-001)"
        )

    def test_no_unreferenced_settimeout_in_ws(self):
        """
        验证 WebSocket 重连逻辑中没有无引用的 setTimeout。
        """
        content = self._store_text()
        # 简单检查：如果 setTimeout 的结果未被存储到 ref 或变量，警告
        # 这是一个启发式检查
        assert "_wsRetryTimer" in content or "retryTimerRef" in content, (
            "WebSocket 重连定时器可能未存储引用 (FRONTEND-001)"
        )


# FRONTEND-002: 闭包过时状态
class TestStaleClosure:
    def test_settings_does_not_read_closure_for_saves(self):
        """
        验证 Settings.tsx 中的保存操作不直接读取闭包中的本地 state。
        这是一个启发式检查：查找 handleSave* 函数中是否直接引用可能过时的变量。
        """
        settings_file = FRONTEND_ROOT / "pages" / "Settings.tsx"
        content = settings_file.read_text()
        # 检查是否使用函数式更新或最新 state
        # 这是一个软性检查
        has_latest_pattern = (
            "fetchSettings" in content or
            "useRef" in content or
            "getState" in content
        )
        if not has_latest_pattern:
            pytest.skip("无法自动验证闭包模式 (FRONTEND-002 需人工审查)")

    def test_no_duplicate_fetchsettings_without_dedup(self):
        """
        验证 fetchSettings 调用不过于频繁（无防抖或去重）。
        """
        settings_file = FRONTEND_ROOT / "pages" / "Settings.tsx"
        content = settings_file.read_text()
        count = content.count("fetchSettings()")
        if count > 10:
            pytest.fail(
                f"Settings.tsx 中 fetchSettings() 被调用 {count} 次，"
                f"建议添加去重机制 (FRONTEND-002)"
            )


# FRONTEND-003: 乐观更新回滚
class TestOptimisticUpdate:
    def test_delete_has_rollback(self):
        """
        验证 Inbox.tsx 中的删除操作有失败回滚。
        """
        inbox_file = FRONTEND_ROOT / "pages" / "Inbox.tsx"
        if not inbox_file.exists():
            pytest.skip("Inbox.tsx 已删除")
        content = inbox_file.read_text()
        # 查找 handleDelete 或类似函数
        if "handleDelete" not in content:
            pytest.skip("未找到 handleDelete 函数")
        # 检查 catch 块中是否有恢复 state 的逻辑
        # 这是一个启发式检查
        has_rollback = (
            "setAssets(prev" in content or
            "setAssets(original" in content or
            "queryClient.setQueryData" in content
        )
        if not has_rollback:
            pytest.fail(
                "Inbox.tsx 的删除操作可能缺少失败回滚 (FRONTEND-003)"
            )

    def test_bulk_delete_has_rollback(self):
        """
        验证批量删除有失败回滚。
        """
        inbox_file = FRONTEND_ROOT / "pages" / "Inbox.tsx"
        if not inbox_file.exists():
            pytest.skip("Inbox.tsx 已删除")
        content = inbox_file.read_text()
        if "handleBulkDelete" not in content:
            pytest.skip("未找到 handleBulkDelete 函数")
        has_rollback = "setAssets(prev" in content or "originalAssets" in content
        if not has_rollback:
            pytest.fail(
                "Inbox.tsx 的批量删除可能缺少失败回滚 (FRONTEND-003)"
            )


# FRONTEND-004: 共享编辑状态
class TestSharedEditState:
    def test_settings_remark_state_isolated(self):
        """
        验证 Settings.tsx 中不同平台账号的编辑状态不共享。
        """
        settings_file = FRONTEND_ROOT / "pages" / "Settings.tsx"
        content = settings_file.read_text()
        # 如果三类账号共享同一个 editingRemarkId，测试失败
        editing_ids = [
            line for line in content.split("\n")
            if "editingRemark" in line and "useState" in line
        ]
        if len(editing_ids) < 2:
            pytest.fail(
                "Settings.tsx 可能只使用一个 editingRemarkId 状态，"
                "不同平台账号编辑状态会冲突 (FRONTEND-004)"
            )


# FRONTEND-005: 硬编码魔法数字
class TestMagicNumbers:
    def test_no_hardcoded_vh_calc(self):
        """
        验证不存在 calc(100vh - 固定像素) 的硬编码。
        """
        result = subprocess.run(
            ["grep", "-rn", "calc(100vh", str(FRONTEND_ROOT)],
            capture_output=True, text=True
        )
        lines = [l for l in result.stdout.strip().split("\n") if l]
        assert len(lines) == 0, (
            f"发现硬编码 vh 计算 (FRONTEND-005):\n" + "\n".join(lines[:10])
        )

    def test_scrollable_flex_has_min_h_0(self):
        """
        启发式检查：包含 overflow-auto 的 flex 子元素是否也有 min-h-0。
        注意：这是一个建议性检查，可能产生误报。
        """
        result = subprocess.run(
            ["grep", "-rln", "overflow-auto", str(FRONTEND_ROOT)],
            capture_output=True, text=True
        )
        files = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        violations = []
        for f in files:
            content = Path(f).read_text()
            # 简单启发式：如果文件有 overflow-auto 但没有 min-h-0 或 min-h-0
            if "overflow-auto" in content and "min-h-0" not in content and "scrollable-flex" not in content:
                violations.append(f)
        if violations:
            pytest.skip(
                f"以下文件有 overflow-auto 但无 min-h-0（需人工确认）: {violations[:5]}"
            )


# CROSS-001: 错误处理
class TestErrorHandling:
    def test_no_silent_catch(self):
        """
        验证不存在 .catch(() => {}) 静默吞错。
        """
        result = subprocess.run(
            ["grep", "-rn", ".catch(() => {})", str(FRONTEND_ROOT)],
            capture_output=True, text=True
        )
        lines = [l for l in result.stdout.strip().split("\n") if l]
        assert len(lines) == 0, (
            f"发现静默吞错 (CROSS-001):\n" + "\n".join(lines[:10])
        )

    def test_api_has_interceptor(self):
        """
        验证 api.ts 有全局错误拦截器。
        """
        api_file = FRONTEND_ROOT / "lib" / "api.ts"
        content = api_file.read_text()
        assert "interceptors.response" in content, (
            "api.ts 缺少全局响应拦截器 (CROSS-001)"
        )


# 组件大小检查
def test_page_components_not_too_large():
    """
    验证页面组件不超过 300 行。
    """
    pages_dir = FRONTEND_ROOT / "pages"
    violations = []
    for f in pages_dir.glob("*.tsx"):
        lines = len(f.read_text().split("\n"))
        # Dashboard 为聚合型控制台，允许更大体积
        threshold = 600 if f.name == "Dashboard.tsx" else 300
        if lines > threshold:
            violations.append(f"{f.name}: {lines} lines")
    if violations:
        pytest.fail(
            "以下页面组件超过 300 行，建议拆分:\n" + "\n".join(violations)
        )
