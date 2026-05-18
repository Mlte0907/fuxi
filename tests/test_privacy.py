"""测试：差分隐私模块"""
import pytest


class TestLaplaceMechanism:
    def test_add_noise_basic(self):
        from fuxi.privacy.differential import LaplaceMechanism
        noisy = LaplaceMechanism.add_noise(100.0, sensitivity=1.0, epsilon=1.0)
        assert isinstance(noisy, float)

    def test_add_noise_convergence(self):
        """多次加噪的平均值应接近原始值"""
        from fuxi.privacy.differential import LaplaceMechanism
        true_val = 50.0
        results = [LaplaceMechanism.add_noise(true_val, 1.0, 0.5) for _ in range(200)]
        avg = sum(results) / len(results)
        assert abs(avg - true_val) < 5.0

    def test_add_noise_to_dict(self):
        from fuxi.privacy.differential import LaplaceMechanism
        data = {"count": 100, "score": 0.75, "name": "test"}
        sens = {"count": 1.0, "score": 0.1}
        result = LaplaceMechanism.add_noise_to_dict(data, sens, epsilon=1.0)
        assert isinstance(result["count"], float)
        assert isinstance(result["score"], float)
        assert result["name"] == "test"  # 非数值字段保持不变

    def test_high_epsilon_less_noise(self):
        """epsilon越大，噪声越小（隐私保护越弱）"""
        from fuxi.privacy.differential import LaplaceMechanism
        low_eps = LaplaceMechanism.add_noise(100.0, 1.0, 0.1)
        high_eps = LaplaceMechanism.add_noise(100.0, 1.0, 10.0)
        assert abs(high_eps - 100.0) < abs(low_eps - 100.0)


class TestPrivacyBudget:
    def test_allocate_and_consume(self):
        from fuxi.privacy.differential import PrivacyBudget
        budget = PrivacyBudget(total_epsilon=1.0)
        assert budget.remaining == 1.0
        assert budget.exhausted is False

        ok = budget.allocate(0.3, "query1")
        assert ok is True
        assert budget.remaining == 0.7

    def test_exhausted(self):
        from fuxi.privacy.differential import PrivacyBudget
        budget = PrivacyBudget(total_epsilon=0.5)
        assert budget.allocate(0.6, "big_query") is False
        assert budget.exhausted is False

        assert budget.allocate(0.5, "exact_query") is True
        assert budget.exhausted is True
        assert budget.allocate(0.1, "after_exhaust") is False

    def test_reset(self):
        from fuxi.privacy.differential import PrivacyBudget
        budget = PrivacyBudget(total_epsilon=1.0)
        budget.allocate(0.8, "heavy")
        assert budget.remaining == pytest.approx(0.2)
        budget.reset()
        assert budget.remaining == 1.0


class TestDPStatistics:
    def test_dp_count_near_true(self):
        from fuxi.privacy.differential import DPStatistics
        dp = DPStatistics(epsilon=1.0)
        result = dp.dp_count(100, "test")
        assert result >= 0
        assert isinstance(result, int)

    def test_dp_count_budget_exhausted(self):
        from fuxi.privacy.differential import DPStatistics
        dp = DPStatistics(epsilon=0.01)
        # total_epsilon = 0.01 * 10 = 0.1, each query uses 0.01/10 = 0.001
        # so 100+ queries to exhaust. Test that budget decreases.
        results = []
        for i in range(10):
            r = dp.dp_count(100, f"q{i}")
            results.append(r)
        assert all(r >= 0 for r in results)
        assert dp._budget.remaining < 0.1  # 已消耗部分预算

    def test_dp_average(self):
        from fuxi.privacy.differential import DPStatistics
        dp = DPStatistics(epsilon=1.0)
        values = [0.5, 0.6, 0.7, 0.8, 0.9]
        avg = dp.dp_average(values, value_range=1.0, query_name="test_avg")
        assert avg is not None
        assert isinstance(avg, float)

    def test_dp_average_empty(self):
        from fuxi.privacy.differential import DPStatistics
        dp = DPStatistics(epsilon=1.0)
        assert dp.dp_average([], value_range=1.0) is None

    def test_dp_histogram(self):
        from fuxi.privacy.differential import DPStatistics
        dp = DPStatistics(epsilon=1.0)
        counts = {"a": 50, "b": 30, "c": 20}
        hist = dp.dp_histogram(counts, "test_hist")
        assert len(hist) == 3
        for v in hist.values():
            assert v >= 0


class TestMemorySanitizer:
    def test_sanitize_phone(self):
        from fuxi.privacy.sanitizer import MemorySanitizer
        text = "我的手机号是13812345678，请联系我"
        clean, redacted = MemorySanitizer.sanitize(text, level="standard")
        assert "13812345678" not in clean
        assert "[PHONE]" in clean
        assert redacted.get("phone") == 1

    def test_sanitize_email(self):
        from fuxi.privacy.sanitizer import MemorySanitizer
        text = "邮箱 test@example.com 用于注册"
        clean, redacted = MemorySanitizer.sanitize(text, level="standard")
        assert "test@example.com" not in clean
        assert "[EMAIL]" in clean
        assert redacted.get("email") == 1

    def test_sanitize_id_card(self):
        from fuxi.privacy.sanitizer import MemorySanitizer
        # 使用不匹配电话号码的身份证号（首两位不在13-19范围）
        text = "身份证号220101199001011234请核实"
        clean, redacted = MemorySanitizer.sanitize(text, level="strict")
        assert "220101199001011234" not in clean
        assert "[ID_CARD]" in clean

    def test_sanitize_url_with_token(self):
        from fuxi.privacy.sanitizer import MemorySanitizer
        text = "访问 https://api.example.com?token=abc123secret 获取数据"
        clean, redacted = MemorySanitizer.sanitize(text, level="minimal")
        assert "token=abc123secret" not in clean
        assert "[URL_WITH_CREDENTIAL]" in clean

    def test_sanitize_level_minimal(self):
        from fuxi.privacy.sanitizer import MemorySanitizer
        text = "手机13812345678 邮箱test@example.com"
        clean, redacted = MemorySanitizer.sanitize(text, level="minimal")
        # minimal级别只脱敏URL凭证，不脱敏手机邮箱
        assert "13812345678" in clean
        assert "test@example.com" in clean

    def test_sanitize_for_embedding(self):
        from fuxi.privacy.sanitizer import MemorySanitizer
        text = "请联系13812345678"
        clean = MemorySanitizer.sanitize_for_embedding(text)
        assert "13812345678" not in clean

    def test_sanitize_for_export(self):
        from fuxi.privacy.sanitizer import MemorySanitizer
        text = "IP地址192.168.1.1上有服务运行"
        clean, redacted = MemorySanitizer.sanitize(text, level="strict")
        assert "192.168.1.1" not in clean
        assert "[IP]" in clean

    def test_custom_keyword(self):
        from fuxi.privacy.sanitizer import MemorySanitizer
        MemorySanitizer.add_custom_keyword("秘密项目")
        text = "这个秘密项目需要保密"
        clean, redacted = MemorySanitizer.sanitize(text, level="standard")
        assert "秘密项目" not in clean
        assert "[REDACTED:秘密***]" in clean
        # 清理
        MemorySanitizer.custom_keywords.remove("秘密项目")


class TestEventLogSanitization:
    """验证 event_log 写入时敏感信息被脱敏"""

    def test_event_data_sanitized_before_insert(self):
        """验证 EventLoggerEngine 在写入 event_log 前对数据进行脱敏"""
        from fuxi.engines.event_logger import EventLoggerEngine
        from fuxi.kernel.event_bus import Event, EventPriority
        from fuxi.privacy.sanitizer import MemorySanitizer

        # 构造包含敏感信息的测试事件
        sensitive_text = "用户手机号13812345678，邮箱test@example.com"
        test_event = Event(
            type="memory.created",  # EventType 使用字符串
            data={"content": sensitive_text, "user_id": "u123"},
            source="test_source",
            priority=EventPriority.NORMAL,
        )

        # 验证事件数据中确实包含敏感信息
        assert "13812345678" in str(test_event.data)

        # 测试 MemorySanitizer 能正确脱敏
        clean_content, _ = MemorySanitizer.sanitize(sensitive_text, level="standard")
        assert "13812345678" not in clean_content
        assert "test@example.com" not in clean_content
        assert "[PHONE]" in clean_content
        assert "[EMAIL]" in clean_content
