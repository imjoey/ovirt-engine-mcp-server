#!/usr/bin/env python3
"""Tests for search_utils module - 搜索工具模块测试."""
import pytest


class TestSanitizeSearchValue:
    """测试 sanitize_search_value 函数"""

    def test_empty_string(self):
        """测试空字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        assert sanitize_search_value("") == ""
        assert sanitize_search_value(None) is None

    def test_simple_string(self):
        """测试简单字符串（无特殊字符）"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("simple_name")
        assert result == "simple_name"

    def test_string_with_spaces(self):
        """测试包含空格的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("my vm name")
        assert result == '"my vm name"'

    def test_string_with_semicolon(self):
        """测试包含分号的字符串（注入攻击）"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        # 分号用于终止搜索条件
        result = sanitize_search_value("vm; delete all")
        assert result == '"vm; delete all"'

    def test_string_with_ampersand(self):
        """测试包含 & 的字符串（注入攻击）"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("vm & host")
        assert result == '"vm & host"'

    def test_string_with_pipe(self):
        """测试包含 | 的字符串（注入攻击）"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("vm | command")
        assert result == '"vm | command"'

    def test_string_with_parentheses(self):
        """测试包含括号的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("(nested)")
        assert result == '"(nested)"'

    def test_string_with_quotes(self):
        """测试包含引号的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        # 引号需要转义
        result = sanitize_search_value('my"vm')
        assert '"' in result
        assert '\\"' in result

    def test_string_with_backslash(self):
        """测试包含反斜杠的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("path\\to\\vm")
        assert "\\\\" in result

    def test_string_with_equals(self):
        """测试包含等号的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("name=value")
        assert result == '"name=value"'

    def test_string_with_less_than(self):
        """测试包含 < 的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("a < b")
        assert result == '"a < b"'

    def test_string_with_greater_than(self):
        """测试包含 > 的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("a > b")
        assert result == '"a > b"'

    def test_string_with_exclamation(self):
        """测试包含 ! 的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("vm!test")
        assert result == '"vm!test"'

    def test_complex_injection_attempt(self):
        """测试复杂的注入攻击尝试"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        # 模拟 SQL 注入风格的攻击
        malicious = "vm'; DROP TABLE vms; --"
        result = sanitize_search_value(malicious)

        # 应该被引号包裹
        assert result.startswith('"')
        assert result.endswith('"')

    def test_unicode_characters(self):
        """测试 Unicode 字符"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        # 中文字符
        result = sanitize_search_value("虚拟机")
        assert result == "虚拟机"

    def test_numeric_string(self):
        """测试数字字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("12345")
        assert result == "12345"

    def test_uuid_format(self):
        """测试 UUID 格式"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        uuid = "12345678-1234-1234-1234-123456789012"
        result = sanitize_search_value(uuid)
        assert result == uuid

    def test_dashes_only(self):
        """测试只包含短横线的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("my-vm-name")
        assert result == "my-vm-name"

    def test_underscores_only(self):
        """测试只包含下划线的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("my_vm_name")
        assert result == "my_vm_name"

    def test_dots_only(self):
        """测试只包含点的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("vm.name.test")
        assert result == "vm.name.test"

    def test_already_quoted(self):
        """测试已包含引号的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value('"already quoted"')
        # 内部引号应该被转义
        assert '\\"' in result

    def test_injection_with_quotes_and_special_chars(self):
        """测试包含引号和特殊字符的注入攻击"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        malicious = 'vm" & "injection'
        result = sanitize_search_value(malicious)
        # 应该被正确转义和包裹
        assert '\\"' in result


class TestSanitizeSearchValueEdgeCases:
    """测试边界情况"""

    def test_very_long_string(self):
        """测试超长字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        long_string = "a" * 10000
        result = sanitize_search_value(long_string)
        assert len(result) >= len(long_string)

    def test_only_special_chars(self):
        """测试只包含特殊字符"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("; & | ( )")
        assert result == '"; & | ( )"'

    def test_whitespace_only(self):
        """测试只包含空白字符"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("   ")
        assert result == '"   "'

    def test_newline_in_string(self):
        """测试包含换行符的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("vm\nname")
        # 换行符不在特殊字符列表中，直接返回
        assert result == "vm\nname"

    def test_tab_in_string(self):
        """测试包含制表符的字符串"""
        from ovirt_engine_mcp_server.search_utils import sanitize_search_value

        result = sanitize_search_value("vm\tname")
        # 制表符不在特殊字符列表中，直接返回
        assert result == "vm\tname"
