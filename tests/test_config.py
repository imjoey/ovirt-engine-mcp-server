#!/usr/bin/env python3
"""Tests for config module - 配置模块测试."""
import pytest
import os
import tempfile
from unittest.mock import patch


class TestConfigDataclass:
    """测试 Config 数据类"""

    def test_config_defaults(self):
        """测试默认配置值"""
        from ovirt_engine_mcp_server.config import Config

        config = Config()

        assert config.ovirt_engine_url == ""
        assert config.ovirt_engine_user == ""
        assert config.ovirt_engine_password == ""
        assert config.ovirt_engine_ca_file == ""
        assert config.ovirt_engine_timeout == 30
        assert config.ovirt_engine_insecure is False
        assert config.mcp_log_level == "INFO"

    def test_config_with_values(self):
        """测试带值的配置"""
        from ovirt_engine_mcp_server.config import Config

        config = Config(
            ovirt_engine_url="https://ovirt.example.com",
            ovirt_engine_user="admin@internal",
            ovirt_engine_password="secret",
            ovirt_engine_timeout=60,
            ovirt_engine_insecure=True,
            mcp_log_level="DEBUG",
        )

        assert config.ovirt_engine_url == "https://ovirt.example.com"
        assert config.ovirt_engine_user == "admin@internal"
        assert config.ovirt_engine_password == "secret"
        assert config.ovirt_engine_timeout == 60
        assert config.ovirt_engine_insecure is True
        assert config.mcp_log_level == "DEBUG"


class TestLoadConfig:
    """测试 load_config 函数"""

    def test_load_config_from_env(self):
        """测试从环境变量加载配置"""
        from ovirt_engine_mcp_server.config import load_config, Config

        env_vars = {
            "OVIRT_ENGINE_URL": "https://ovirt.env.test",
            "OVIRT_ENGINE_USER": "env_user",
            "OVIRT_ENGINE_PASSWORD": "env_pass",
            "OVIRT_ENGINE_TIMEOUT": "45",
            "OVIRT_ENGINE_INSECURE": "true",
            "MCP_LOG_LEVEL": "WARNING",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            # 不存在的配置文件路径，只从环境变量加载
            config = load_config("/nonexistent/config.yaml")

        assert config.ovirt_engine_url == "https://ovirt.env.test"
        assert config.ovirt_engine_user == "env_user"
        assert config.ovirt_engine_password == "env_pass"
        assert config.ovirt_engine_timeout == 45
        assert config.ovirt_engine_insecure is True
        assert config.mcp_log_level == "WARNING"

    def test_load_config_from_yaml(self):
        """测试从 YAML 文件加载配置"""
        from ovirt_engine_mcp_server.config import load_config

        yaml_content = """
ovirt_engine_url: https://ovirt.yaml.test
ovirt_engine_user: yaml_user
ovirt_engine_password: yaml_pass
ovirt_engine_timeout: 50
mcp_log_level: ERROR
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            config = load_config(f.name)

        assert config.ovirt_engine_url == "https://ovirt.yaml.test"
        assert config.ovirt_engine_user == "yaml_user"
        assert config.ovirt_engine_password == "yaml_pass"
        assert config.ovirt_engine_timeout == 50
        assert config.mcp_log_level == "ERROR"

    def test_load_config_env_overrides_yaml(self):
        """测试环境变量覆盖 YAML 配置"""
        from ovirt_engine_mcp_server.config import load_config

        yaml_content = """
ovirt_engine_url: https://ovirt.yaml.test
ovirt_engine_user: yaml_user
ovirt_engine_timeout: 50
"""

        env_vars = {
            "OVIRT_ENGINE_USER": "env_override_user",
            "OVIRT_ENGINE_TIMEOUT": "99",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            with patch.dict(os.environ, env_vars, clear=False):
                config = load_config(f.name)

        # 环境变量覆盖
        assert config.ovirt_engine_user == "env_override_user"
        assert config.ovirt_engine_timeout == 99
        # YAML 值保留
        assert config.ovirt_engine_url == "https://ovirt.yaml.test"

    def test_load_config_missing_file(self):
        """测试配置文件不存在时使用默认值"""
        from ovirt_engine_mcp_server.config import load_config

        # 清理环境变量
        env_vars = {k: "" for k in [
            "OVIRT_ENGINE_URL", "OVIRT_ENGINE_USER", "OVIRT_ENGINE_PASSWORD",
            "OVIRT_ENGINE_CA_FILE", "OVIRT_ENGINE_TIMEOUT", "OVIRT_ENGINE_INSECURE",
            "MCP_LOG_LEVEL"
        ]}

        with patch.dict(os.environ, env_vars, clear=True):
            config = load_config("/nonexistent/config.yaml")

        # 使用默认值
        assert config.ovirt_engine_url == ""
        assert config.ovirt_engine_timeout == 30

    def test_load_config_invalid_yaml(self):
        """测试无效 YAML 文件"""
        from ovirt_engine_mcp_server.config import load_config

        invalid_yaml = """
this is not: valid yaml: : :
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(invalid_yaml)
            f.flush()
            # 不应该抛出异常，使用默认值
            config = load_config(f.name)

        assert config is not None


class TestConvertValue:
    """测试 _convert_value 函数"""

    def test_convert_bool_from_string_true(self):
        """测试从字符串转换为布尔值 True"""
        from ovirt_engine_mcp_server.config import _convert_value

        assert _convert_value("true", bool) is True
        assert _convert_value("True", bool) is True
        assert _convert_value("TRUE", bool) is True
        assert _convert_value("1", bool) is True
        assert _convert_value("yes", bool) is True
        assert _convert_value("on", bool) is True

    def test_convert_bool_from_string_false(self):
        """测试从字符串转换为布尔值 False"""
        from ovirt_engine_mcp_server.config import _convert_value

        assert _convert_value("false", bool) is False
        assert _convert_value("False", bool) is False
        assert _convert_value("0", bool) is False
        assert _convert_value("no", bool) is False

    def test_convert_bool_from_bool(self):
        """测试布尔值保持不变"""
        from ovirt_engine_mcp_server.config import _convert_value

        assert _convert_value(True, bool) is True
        assert _convert_value(False, bool) is False

    def test_convert_int_from_string(self):
        """测试从字符串转换为整数"""
        from ovirt_engine_mcp_server.config import _convert_value

        assert _convert_value("42", int) == 42
        assert _convert_value("0", int) == 0
        assert _convert_value("-10", int) == -10

    def test_convert_string(self):
        """测试字符串保持不变"""
        from ovirt_engine_mcp_server.config import _convert_value

        assert _convert_value("hello", str) == "hello"
        assert _convert_value(123, str) == "123"

    def test_convert_none(self):
        """测试 None 值"""
        from ovirt_engine_mcp_server.config import _convert_value

        assert _convert_value(None, str) is None
        assert _convert_value(None, int) is None
        assert _convert_value(None, bool) is None


class TestSanitizeLogMessage:
    """测试 sanitize_log_message 函数"""

    def test_sanitize_password(self):
        """测试脱敏密码"""
        from ovirt_engine_mcp_server.config import sanitize_log_message

        msg = "Connection with password=secret123 failed"
        result = sanitize_log_message(msg)

        assert "secret123" not in result
        assert "***" in result

    def test_sanitize_password_colon(self):
        """测试脱敏密码（冒号格式）"""
        from ovirt_engine_mcp_server.config import sanitize_log_message

        msg = "Error: password: mypassword"
        result = sanitize_log_message(msg)

        assert "mypassword" not in result

    def test_sanitize_api_key(self):
        """测试脱敏 API Key"""
        from ovirt_engine_mcp_server.config import sanitize_log_message

        msg = "Using api_key=abc123xyz"
        result = sanitize_log_message(msg)

        assert "abc123xyz" not in result
        assert "***" in result

    def test_sanitize_token(self):
        """测试脱敏 Token"""
        from ovirt_engine_mcp_server.config import sanitize_log_message

        msg = "Auth token=bearer_token_here"
        result = sanitize_log_message(msg)

        assert "bearer_token_here" not in result

    def test_sanitize_secret(self):
        """测试脱敏 Secret"""
        from ovirt_engine_mcp_server.config import sanitize_log_message

        msg = "secret=my_secret_value"
        result = sanitize_log_message(msg)

        assert "my_secret_value" not in result

    def test_no_sensitive_data(self):
        """测试无敏感数据的消息"""
        from ovirt_engine_mcp_server.config import sanitize_log_message

        msg = "Connected to server successfully"
        result = sanitize_log_message(msg)

        assert result == msg

    def test_case_insensitive(self):
        """测试大小写不敏感"""
        from ovirt_engine_mcp_server.config import sanitize_log_message

        msg = "PASSWORD=Secret123 and Api_Key=xyz"
        result = sanitize_log_message(msg)

        assert "Secret123" not in result
        assert "xyz" not in result


class TestSensitiveFields:
    """测试敏感字段定义"""

    def test_sensitive_fields_defined(self):
        """测试敏感字段列表已定义"""
        from ovirt_engine_mcp_server.config import SENSITIVE_FIELDS

        assert "ovirt_engine_password" in SENSITIVE_FIELDS
