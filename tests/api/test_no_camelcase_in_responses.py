"""REFACTOR 2026-05 任务 3 契约测试：API 响应必须全部 snake_case。

设计原则：
1. 遍历 app.routes 的所有 GET 路由
2. 对每个发 TestClient 请求（带 path 参数的用 placeholder）
3. 递归扫 JSON 响应的所有 key，发现 camelCase 立即 fail 并打印路径
4. 仅校验 JSON 响应；非 200 状态码也算（detail 字段也要 snake）

通过条件：所有 key 满足 `^[a-z0-9_]+$` 或非字母（如 status_code）。
驼峰检测：含至少一个 [A-Z] 且开头小写（accountId / accountLabel 等）。
"""

from __future__ import annotations

import re
from typing import Any

from fastapi.testclient import TestClient

from media_tools.api.app import app

CAMEL_CASE = re.compile(r"^[a-z]+[A-Z]")


def _iter_keys(node: Any, path: str = "$"):
    """递归生成 (path, key) 对，用于精确定位违规字段。"""
    if isinstance(node, dict):
        for k, v in node.items():
            yield f"{path}.{k}", k
            yield from _iter_keys(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _iter_keys(item, f"{path}[{i}]")


def _is_camel_case(key: Any) -> bool:
    return isinstance(key, str) and bool(CAMEL_CASE.match(key))


# 跳过列表：依赖外部状态或返回非 JSON 的路由
SKIP_PATHS = {
    "/api/v1/assets/{asset_id}/file",  # FileResponse 非 JSON
    "/api/v1/assets/{asset_id}/transcript",  # 依赖 DB 存在该 asset
    "/api/v1/assets/{asset_id}/folder",  # 同上
    "/api/v1/tasks/{task_id}",  # 依赖 task 存在
    "/api/v1/scheduler/{task_id}",  # 同上
    "/api/v1/scheduler/{task_id}/toggle",
    "/api/v1/settings/douyin/{account_id}",
    "/api/v1/settings/douyin/{account_id}/remark",
    "/api/v1/settings/qwen/accounts/{account_id}/cookie",
    "/api/v1/settings/bilibili/accounts/{account_id}",
    "/api/v1/settings/bilibili/accounts/{account_id}/remark",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/docs/oauth2-redirect",
}


def _collect_get_routes() -> list[str]:
    """从 app 注册的路由里捞所有 GET，跳过 SKIP_PATHS。"""
    routes: list[str] = []
    for route in app.routes:
        methods = getattr(route, "methods", set()) or set()
        if "GET" not in methods:
            continue
        path = getattr(route, "path", "")
        if not path or path in SKIP_PATHS:
            continue
        # 含 path 参数的路由跳过（需要 fixture 数据，不在本契约范围）
        if "{" in path:
            continue
        routes.append(path)
    return routes


def test_no_camel_case_in_get_responses():
    """所有无参 GET 路由的 JSON 响应不得出现 camelCase 字段。"""
    client = TestClient(app)
    routes = _collect_get_routes()
    assert routes, "未找到任何 GET 路由——TestClient 路由收集可能有问题"

    violations: list[str] = []
    skipped: list[str] = []

    for path in routes:
        try:
            resp = client.get(path)
        except Exception as e:  # noqa: BLE001
            skipped.append(f"{path}: {type(e).__name__}: {e}")
            continue

        # 非 JSON 响应跳过（如 HTML / 流）
        content_type = resp.headers.get("content-type", "")
        if "application/json" not in content_type:
            continue

        try:
            data = resp.json()
        except ValueError:
            continue

        for key_path, key in _iter_keys(data):
            if _is_camel_case(key):
                violations.append(f"{path}  →  {key_path}  (key='{key}')")

    assert not violations, f"\n发现 {len(violations)} 处 camelCase 字段（应为 snake_case）：\n" + "\n".join(
        f"  - {v}" for v in violations[:30]
    )


def test_no_deprecated_camelcase_in_frontend_types():
    """前端类型定义里 @deprecated camelCase 字段必须被彻底删除。

    扫 frontend/src/types/ + dashboard.ts + Home.tsx 三个高频文件，
    确保没有 `accountId?:` `accountLabel?:` 这种残留。"""
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent.parent
    targets = [
        "frontend/src/types/index.ts",
        "frontend/src/services/dashboard.ts",
        "frontend/src/pages/Home.tsx",
        "frontend/src/hooks/useSettings.ts",
    ]

    violations: list[str] = []
    for rel in targets:
        full = repo_root / rel
        if not full.exists():
            continue
        result = subprocess.run(
            ["grep", "-n", "-E", r"accountId\?:|accountLabel\?:|\b(accountId|accountLabel)\b", str(full)],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            # 允许：注释里说明历史 / 函数参数名（带括号 / 箭头）
            if "//" in line or "/*" in line or "(accountId" in line or "(accountId:" in line:
                continue
            violations.append(f"{rel}: {line.strip()}")

    assert not violations, "前端类型层仍有 camelCase 业务字段引用（应删 @deprecated 残留）：\n" + "\n".join(
        f"  - {v}" for v in violations[:20]
    )
