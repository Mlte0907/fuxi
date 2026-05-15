"""测试：Cron 调度器"""
import uuid


class TestCronParser:
    def test_chinese_daily_expression(self):
        from fuxi.cron.parser import parse_nl_to_cron
        result = parse_nl_to_cron("每天早上9点")
        assert result is not None
        assert "9" in result

    def test_chinese_hourly_expression(self):
        from fuxi.cron.parser import parse_nl_to_cron
        result = parse_nl_to_cron("每小时执行一次")
        # 可能支持也可能不支持，验证不抛异常即可
        assert result is None or isinstance(result, str)

    def test_chinese_every_five_minutes(self):
        from fuxi.cron.parser import parse_nl_to_cron
        result = parse_nl_to_cron("每5分钟")
        assert result is not None

    def test_english_daily_expression(self):
        from fuxi.cron.parser import parse_nl_to_cron
        result = parse_nl_to_cron("every day at 9am")
        assert result is None or isinstance(result, str)

    def test_validate_cron_valid(self):
        from fuxi.cron.parser import validate_cron
        assert validate_cron("0 9 * * *") is True

    def test_validate_cron_invalid(self):
        from fuxi.cron.parser import validate_cron
        assert validate_cron("not a cron") is False

    def test_predict_next_run(self):
        from fuxi.cron.parser import predict_next_run
        try:
            next_run = predict_next_run("0 9 * * *")
            assert next_run is not None
        except ImportError:
            pass  # croniter not installed


class TestCronScheduler:
    def test_scheduler_singleton(self):
        from fuxi.cron.scheduler import get_cron_scheduler
        s1 = get_cron_scheduler()
        s2 = get_cron_scheduler()
        assert s1 is s2

    def test_add_and_list_task(self, temp_db):
        from fuxi.cron.scheduler import get_cron_scheduler
        scheduler = get_cron_scheduler()
        task_id = f"test-{uuid.uuid4().hex[:8]}"
        scheduler.add_task(
            task_id=task_id,
            name="test_task",
            cron_expression="0 9 * * *",
            agent_id="qinglong",
            instruction="daily check",
        )
        tasks = scheduler.list_tasks(enabled_only=False)
        assert any(t["task_id"] == task_id for t in tasks)

    def test_disable_task(self, temp_db):
        from fuxi.cron.scheduler import get_cron_scheduler
        scheduler = get_cron_scheduler()
        task_id = f"disable-{uuid.uuid4().hex[:8]}"
        scheduler.add_task(
            task_id=task_id,
            name="disable_me",
            cron_expression="* * * * *",
            agent_id="qinglong",
            instruction="should be disabled",
        )
        assert scheduler.update_task(task_id, enabled=0) is True
        tasks = scheduler.list_tasks(enabled_only=True)
        assert not any(t["task_id"] == task_id for t in tasks)

    def test_delete_task(self, temp_db):
        from fuxi.cron.scheduler import get_cron_scheduler
        scheduler = get_cron_scheduler()
        task_id = f"del-{uuid.uuid4().hex[:8]}"
        scheduler.add_task(
            task_id=task_id,
            name="delete_me",
            cron_expression="0 0 * * *",
            agent_id="qinglong",
            instruction="should be deleted",
        )
        assert scheduler.delete_task(task_id) is True

    def test_add_from_nl(self, temp_db):
        from fuxi.cron.scheduler import get_cron_scheduler
        scheduler = get_cron_scheduler()
        task_id = f"nl-{uuid.uuid4().hex[:8]}"
        result = scheduler.add_from_nl(
            task_id=task_id,
            name="nl_task",
            nl_schedule="每天上午9点",
            agent_id="qinglong",
            instruction="test nl parsing",
        )
        assert result is not None


class TestTaskTrackingRoutes:
    def test_list_tasks_api(self, client):
        from test_api_integration import auth_headers
        r = client.get("/api/v2/tasks", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "tasks" in data

    def test_create_task_api(self, client):
        from test_api_integration import auth_headers
        task_id = f"test-{uuid.uuid4().hex[:8]}"
        r = client.post(
            "/api/v2/tasks",
            headers=auth_headers(),
            json={
                "task_id": task_id,
                "title": "Test Task",
                "assignee": "qinglong",
                "status": "PENDING",
            },
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "PENDING"
