#!/usr/bin/env python3
"""Tests for healthcheck module - 健康检查模块测试."""
import pytest
from unittest.mock import MagicMock, patch
import sys


class TestCheckOvirtConnection:
    """测试 check_ovirt_connection 函数"""

    def test_missing_url(self):
        """测试缺少 URL 配置"""
        # 使用 patch 在模块级别 mock
        with patch.dict(sys.modules, {'ovirtsdk4': MagicMock()}):
            from src.healthcheck import check_ovirt_connection
            from src.config import Config

            config = Config()  # 空 URL

            result = check_ovirt_connection(config)

            assert result is False

    def test_missing_user(self):
        """测试缺少用户配置"""
        with patch.dict(sys.modules, {'ovirtsdk4': MagicMock()}):
            from src.healthcheck import check_ovirt_connection
            from src.config import Config

            config = Config(
                ovirt_engine_url="https://ovirt.test",
                # 缺少用户
            )

            result = check_ovirt_connection(config)

            assert result is False

    def test_missing_password(self):
        """测试缺少密码配置"""
        with patch.dict(sys.modules, {'ovirtsdk4': MagicMock()}):
            from src.healthcheck import check_ovirt_connection
            from src.config import Config

            config = Config(
                ovirt_engine_url="https://ovirt.test",
                ovirt_engine_user="admin@internal",
                # 缺少密码
            )

            result = check_ovirt_connection(config)

            assert result is False


class TestHealthcheckMain:
    """测试 main 函数"""

    @patch.dict(sys.modules, {'ovirtsdk4': MagicMock()})
    @patch("src.healthcheck.load_config")
    @patch("src.healthcheck.check_ovirt_connection")
    def test_main_success(self, mock_check, mock_load_config):
        """测试 main 函数成功"""
        from src.healthcheck import main
        from src.config import Config

        mock_config = Config(
            ovirt_engine_url="https://ovirt.test",
            ovirt_engine_user="admin@internal",
            ovirt_engine_password="secret",
        )
        mock_load_config.return_value = mock_config
        mock_check.return_value = True

        # main() 成功时会调用 sys.exit(0)
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0

    @patch.dict(sys.modules, {'ovirtsdk4': MagicMock()})
    @patch("src.healthcheck.load_config")
    def test_main_config_error(self, mock_load_config):
        """测试 main 函数配置错误"""
        from src.healthcheck import main

        mock_load_config.side_effect = Exception("Config error")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    @patch.dict(sys.modules, {'ovirtsdk4': MagicMock()})
    @patch("src.healthcheck.load_config")
    @patch("src.healthcheck.check_ovirt_connection")
    def test_main_connection_failed(self, mock_check, mock_load_config):
        """测试 main 函数连接失败"""
        from src.healthcheck import main
        from src.config import Config

        mock_config = Config(
            ovirt_engine_url="https://ovirt.test",
            ovirt_engine_user="admin@internal",
            ovirt_engine_password="secret",
        )
        mock_load_config.return_value = mock_config
        mock_check.return_value = False

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1


class TestHealthcheckModuleImport:
    """测试模块导入"""

    def test_import_success(self):
        """测试模块导入成功"""
        with patch.dict(sys.modules, {'ovirtsdk4': MagicMock()}):
            # 应该能够成功导入
            from src import healthcheck

            assert hasattr(healthcheck, "check_ovirt_connection")
            assert hasattr(healthcheck, "main")
