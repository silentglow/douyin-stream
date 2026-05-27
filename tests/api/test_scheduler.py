"""Scheduler API 测试"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from media_tools.api.app import app
from media_tools.store.db import get_db_connection

client = TestClient(app)


def _clear_scheduled_tasks():
    """清理所有用户创建的调度任务（保留系统任务 __xxx__）"""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM scheduled_tasks WHERE task_id NOT GLOB '__*'")
        conn.commit()


class TestSchedulerAPI:
    """测试调度器 CRUD 端点"""

    def setup_method(self):
        _clear_scheduled_tasks()

    def teardown_method(self):
        _clear_scheduled_tasks()

    def test_list_schedules_empty(self):
        """空列表返回空数组"""
        response = client.get("/api/v1/scheduler")
        assert response.status_code == 200
        assert response.json() == []

    def test_add_schedule_success(self):
        """添加有效的 cron 调度任务"""
        response = client.post(
            "/api/v1/scheduler",
            json={
                "cron_expr": "0 2 * * *",
                "enabled": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "task_id" in data

        # 验证列表中包含新任务
        list_resp = client.get("/api/v1/scheduler")
        assert list_resp.status_code == 200
        tasks = list_resp.json()
        assert len(tasks) == 1
        assert tasks[0]["cron_expr"] == "0 2 * * *"
        assert tasks[0]["enabled"] is True
        assert tasks[0]["task_type"] == "scan_all_following"

        # 清理
        client.delete(f"/api/v1/scheduler/{tasks[0]['task_id']}")

    def test_add_schedule_invalid_cron(self):
        """无效的 cron 表达式返回 400"""
        response = client.post(
            "/api/v1/scheduler",
            json={
                "cron_expr": "invalid",
                "enabled": True,
            },
        )
        assert response.status_code == 400
        assert "Invalid cron" in response.json()["message"]

    def test_toggle_schedule(self):
        """切换调度任务启用状态"""
        # 先创建
        create_resp = client.post(
            "/api/v1/scheduler",
            json={
                "cron_expr": "0 3 * * *",
                "enabled": True,
            },
        )
        task_id = create_resp.json()["task_id"]

        # 禁用
        toggle_resp = client.put(f"/api/v1/scheduler/{task_id}/toggle", json={"enabled": False})
        assert toggle_resp.status_code == 200
        assert toggle_resp.json()["status"] == "success"

        # 验证状态
        list_resp = client.get("/api/v1/scheduler")
        tasks = list_resp.json()
        task = next(t for t in tasks if t["task_id"] == task_id)
        assert task["enabled"] is False

        # 再启用
        toggle_resp = client.put(f"/api/v1/scheduler/{task_id}/toggle", json={"enabled": True})
        assert toggle_resp.status_code == 200

        list_resp = client.get("/api/v1/scheduler")
        tasks = list_resp.json()
        task = next(t for t in tasks if t["task_id"] == task_id)
        assert task["enabled"] is True

        # 清理
        client.delete(f"/api/v1/scheduler/{task_id}")

    def test_toggle_nonexistent_schedule(self):
        """切换不存在的任务返回 404"""
        response = client.put("/api/v1/scheduler/nonexistent-id/toggle", json={"enabled": False})
        assert response.status_code == 404

    def test_delete_schedule(self):
        """删除调度任务"""
        create_resp = client.post(
            "/api/v1/scheduler",
            json={
                "cron_expr": "0 4 * * *",
                "enabled": True,
            },
        )
        task_id = create_resp.json()["task_id"]

        delete_resp = client.delete(f"/api/v1/scheduler/{task_id}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["status"] == "success"

        # 验证已删除
        list_resp = client.get("/api/v1/scheduler")
        assert list_resp.json() == []

    def test_delete_nonexistent_schedule(self):
        """删除不存在的任务返回 404"""
        response = client.delete("/api/v1/scheduler/nonexistent-id")
        assert response.status_code == 404

    def test_run_now(self):
        """触发立即运行返回成功"""
        with patch("media_tools.api.routers.scheduler._run_scan_all_following") as mock_run:
            response = client.post("/api/v1/scheduler/run_now")
            assert response.status_code == 200
            assert response.json()["status"] == "success"
            mock_run.assert_called_once()  # TestClient 会同步执行 BackgroundTasks
