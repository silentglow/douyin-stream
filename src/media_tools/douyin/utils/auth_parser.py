import json
import re
from typing import Any

import yaml

from media_tools.logger import get_logger

logger = get_logger(__name__)
from media_tools.douyin.core.config_mgr import get_config

PROJECT_ROOT = get_config().project_root
RULES_PATH = PROJECT_ROOT / "config" / "auth_rules.yaml"


class AuthParser:
    def __init__(self):
        self.rules = self._load_rules()

    def _load_rules(self) -> dict[str, Any]:
        if not RULES_PATH.exists():
            return {}
        try:
            with open(RULES_PATH, encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("rules", {})
        except (OSError, yaml.YAMLError):
            return {}

    def parse_cookie(self, raw_data: str, rule_name: str = "douyin") -> tuple[bool, str, dict[str, str]]:
        """解析 Cookie 字符串并验证"""
        rule = self.rules.get(rule_name, {})
        if not rule or rule.get("type") != "cookie":
            return False, "无效的规则", {}

        cookies = {}
        for item in raw_data.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                cookies[k.strip()] = v.strip()

        # 验证必填字段
        required = rule.get("required_keys", [])
        for key in required:
            if key not in cookies:
                return False, f"缺少必填字段: {key}", cookies

        # 验证长度
        min_length = rule.get("validation", {}).get("min_length", 0)
        if len(raw_data) < min_length:
            return False, f"Cookie 长度过短 (<{min_length})", cookies

        return True, "解析成功", cookies

    def _get_nested_value(self, data: dict, path: str) -> Any:
        keys = path.split(".")
        val = data
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return None
        return val

    def parse_json(self, raw_data: str, rule_name: str = "custom_json") -> tuple[bool, str, dict[str, str]]:
        """解析 JSON 并提取映射字段"""
        rule = self.rules.get(rule_name, {})
        if not rule or rule.get("type") != "json":
            return False, "无效的规则", {}

        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            return False, "非法的 JSON 格式", {}

        mapping = rule.get("mapping", {})
        result = {}
        for target_key, json_path in mapping.items():
            val = self._get_nested_value(data, json_path)
            if val is not None:
                result[target_key] = str(val)

        if not result:
            return False, "未能提取任何有效字段", {}

        return True, "解析成功", result

    def parse_text(self, raw_data: str, rule_name: str = "custom_text") -> tuple[bool, str, dict[str, str]]:
        """解析纯文本并提取正则字段"""
        rule = self.rules.get(rule_name, {})
        if not rule or rule.get("type") != "text":
            return False, "无效的规则", {}

        mapping = rule.get("mapping", {})
        result = {}
        for target_key, pattern in mapping.items():
            match = re.search(pattern, raw_data)
            if match:
                result[target_key] = match.group(1)

        if not result:
            return False, "未能提取任何有效字段", {}

        return True, "解析成功", result

    def validate_data(self, raw_data: str, data_type: str = "cookie", rule_name: str | None = None) -> tuple[bool, str]:
        """统一入口：验证与解析"""
        if data_type == "cookie":
            return self.parse_cookie(raw_data, rule_name or "douyin")
        elif data_type == "json":
            return self.parse_json(raw_data, rule_name or "custom_json")
        elif data_type == "text":
            return self.parse_text(raw_data, rule_name or "custom_text")
        else:
            return False, "不支持的数据类型", {}


# 测试用例
if __name__ == "__main__":
    parser = AuthParser()
    success, msg, data = parser.validate_data("sessionid=12345; passport_csrf_token=abc", "cookie", "douyin")
    logger.info(f"Cookie 解析: {success}, {msg}, {data}")
