#!/usr/bin/env python3
"""Tests for EventsMCP class - 事件管理模块测试."""
import pytest
from unittest.mock import MagicMock
from datetime import datetime


def _create_mock_event(event_id="event-123", description="Test event", severity="normal"):
    """创建 mock Event 对象"""
    mock_event = MagicMock()
    mock_event.id = event_id
    mock_event.code = 1000
    mock_event.description = description
    mock_event.severity = MagicMock()
    mock_event.severity.value = severity
    mock_event.time = datetime.now()
    mock_event.user = MagicMock()
    mock_event.user.name = "admin"
    mock_event.user.id = "user-123"
    mock_event.cluster = None
    mock_event.host = None
    mock_event.vm = None
    mock_event.data_center = None
    mock_event.origin = "system"
    mock_event.custom_id = ""
    return mock_event


class TestEventsMCPListEvents:
    """测试 list_events 方法"""

    def test_list_events_empty(self):
        """测试空事件列表"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_events_service = MagicMock()
        mock_events_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.events_service.return_value = mock_events_service

        events_mcp = EventsMCP(mock_ovirt)
        result = events_mcp.list_events()

        assert result == []

    def test_list_events_with_data(self):
        """测试有数据的事件列表"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP

        mock_events = [
            _create_mock_event("event-1", "VM started", "normal"),
            _create_mock_event("event-2", "Host down", "error"),
        ]

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_events_service = MagicMock()
        mock_events_service.list.return_value = mock_events

        mock_ovirt.connection.system_service.return_value.events_service.return_value = mock_events_service

        events_mcp = EventsMCP(mock_ovirt)
        result = events_mcp.list_events()

        assert len(result) == 2
        assert result[0]["description"] == "VM started"
        assert result[1]["severity"] == "error"

    def test_list_events_with_severity_filter(self):
        """测试按严重级别过滤事件"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP

        mock_events = [
            _create_mock_event("event-1", "Alert 1", "alert"),
            _create_mock_event("event-2", "Normal 1", "normal"),
            _create_mock_event("event-3", "Alert 2", "alert"),
        ]

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_events_service = MagicMock()
        mock_events_service.list.return_value = mock_events

        mock_ovirt.connection.system_service.return_value.events_service.return_value = mock_events_service

        events_mcp = EventsMCP(mock_ovirt)
        result = events_mcp.list_events(severity="alert")

        assert len(result) == 2
        for event in result:
            assert event["severity"] == "alert"

    def test_list_events_with_pagination(self):
        """测试分页获取事件"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP

        mock_events = [_create_mock_event(f"event-{i}", f"Event {i}", "normal") for i in range(10)]

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_events_service = MagicMock()
        mock_events_service.list.return_value = mock_events

        mock_ovirt.connection.system_service.return_value.events_service.return_value = mock_events_service

        events_mcp = EventsMCP(mock_ovirt)
        result = events_mcp.list_events(page=2, page_size=3)

        # 应该返回第 4-6 条（索引 3-5）
        assert len(result) == 3

    def test_list_events_not_connected(self):
        """测试未连接时抛出异常"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP
        from ovirt_engine_mcp_server.errors import OvirtConnectionError

        mock_ovirt = MagicMock()
        mock_ovirt.connected = False

        events_mcp = EventsMCP(mock_ovirt)

        with pytest.raises(OvirtConnectionError):
            events_mcp.list_events()


class TestEventsMCPGetAlerts:
    """测试 get_alerts 方法"""

    def test_get_alerts(self):
        """测试获取告警事件"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP

        mock_events = [
            _create_mock_event("event-1", "Alert 1", "alert"),
            _create_mock_event("event-2", "Normal 1", "normal"),
        ]

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_events_service = MagicMock()
        mock_events_service.list.return_value = mock_events

        mock_ovirt.connection.system_service.return_value.events_service.return_value = mock_events_service

        events_mcp = EventsMCP(mock_ovirt)
        result = events_mcp.get_alerts()

        assert len(result) == 1
        assert result[0]["severity"] == "alert"


class TestEventsMCPGetErrors:
    """测试 get_errors 方法"""

    def test_get_errors(self):
        """测试获取错误事件"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP

        mock_events = [
            _create_mock_event("event-1", "Error 1", "error"),
            _create_mock_event("event-2", "Normal 1", "normal"),
            _create_mock_event("event-3", "Error 2", "error"),
        ]

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_events_service = MagicMock()
        mock_events_service.list.return_value = mock_events

        mock_ovirt.connection.system_service.return_value.events_service.return_value = mock_events_service

        events_mcp = EventsMCP(mock_ovirt)
        result = events_mcp.get_errors()

        assert len(result) == 2


class TestEventsMCPGetWarnings:
    """测试 get_warnings 方法"""

    def test_get_warnings(self):
        """测试获取警告事件"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP

        mock_events = [
            _create_mock_event("event-1", "Warning 1", "warning"),
            _create_mock_event("event-2", "Normal 1", "normal"),
        ]

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_events_service = MagicMock()
        mock_events_service.list.return_value = mock_events

        mock_ovirt.connection.system_service.return_value.events_service.return_value = mock_events_service

        events_mcp = EventsMCP(mock_ovirt)
        result = events_mcp.get_warnings()

        assert len(result) == 1
        assert result[0]["severity"] == "warning"


class TestEventsMCPGetEvent:
    """测试 get_event 方法"""

    def test_get_event_success(self):
        """测试获取单个事件详情"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP

        mock_event = _create_mock_event()
        mock_event.cluster = MagicMock()
        mock_event.cluster.name = "Default"
        mock_event.cluster.id = "cluster-123"
        mock_event.host = MagicMock()
        mock_event.host.name = "host1"
        mock_event.host.id = "host-123"
        mock_event.vm = MagicMock()
        mock_event.vm.name = "vm1"
        mock_event.vm.id = "vm-123"

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_event_service = MagicMock()
        mock_event_service.get.return_value = mock_event

        mock_events_service = MagicMock()
        mock_events_service.event_service.return_value = mock_event_service

        mock_ovirt.connection.system_service.return_value.events_service.return_value = mock_events_service

        events_mcp = EventsMCP(mock_ovirt)
        result = events_mcp.get_event("event-123")

        assert result is not None
        assert result["id"] == "event-123"
        assert result["cluster"] == "Default"
        assert result["host"] == "host1"
        assert result["vm"] == "vm1"

    def test_get_event_not_found(self):
        """测试事件不存在"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_event_service = MagicMock()
        mock_event_service.get.side_effect = Exception("Not found")

        mock_events_service = MagicMock()
        mock_events_service.event_service.return_value = mock_event_service

        mock_ovirt.connection.system_service.return_value.events_service.return_value = mock_events_service

        events_mcp = EventsMCP(mock_ovirt)
        result = events_mcp.get_event("nonexistent")

        assert result is None


class TestEventsMCPSearchEvents:
    """测试 search_events 方法"""

    def test_search_events(self):
        """测试搜索事件"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP

        mock_events = [
            _create_mock_event("event-1", "VM started", "normal"),
        ]

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_events_service = MagicMock()
        mock_events_service.list.return_value = mock_events

        mock_ovirt.connection.system_service.return_value.events_service.return_value = mock_events_service

        events_mcp = EventsMCP(mock_ovirt)
        result = events_mcp.search_events("vm.name = test-vm")

        assert len(result) == 1


class TestEventsMCPGetEventsSummary:
    """测试 get_events_summary 方法"""

    def test_get_events_summary(self):
        """测试获取事件统计摘要"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP

        mock_events = [
            _create_mock_event("event-1", "Alert 1", "alert"),
            _create_mock_event("event-2", "Error 1", "error"),
            _create_mock_event("event-3", "Warning 1", "warning"),
            _create_mock_event("event-4", "Normal 1", "normal"),
            _create_mock_event("event-5", "Normal 2", "normal"),
        ]

        # 添加集群信息
        mock_events[0].cluster = MagicMock()
        mock_events[0].cluster.name = "Cluster1"
        mock_events[4].cluster = MagicMock()
        mock_events[4].cluster.name = "Cluster1"

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_events_service = MagicMock()
        mock_events_service.list.return_value = mock_events

        mock_ovirt.connection.system_service.return_value.events_service.return_value = mock_events_service

        events_mcp = EventsMCP(mock_ovirt)
        result = events_mcp.get_events_summary()

        assert result["total"] == 5
        assert result["alert"] == 1
        assert result["error"] == 1
        assert result["warning"] == 1
        assert result["normal"] == 2
        assert "Cluster1" in result["by_cluster"]


class TestEventsMCPAcknowledgeEvent:
    """测试 acknowledge_event 方法"""

    def test_acknowledge_event_success(self):
        """测试确认事件成功"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP

        mock_event = _create_mock_event()
        mock_event.acknowledged = False

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_event_service = MagicMock()
        mock_event_service.get.return_value = mock_event

        mock_events_service = MagicMock()
        mock_events_service.event_service.return_value = mock_event_service

        mock_ovirt.connection.system_service.return_value.events_service.return_value = mock_events_service

        events_mcp = EventsMCP(mock_ovirt)
        result = events_mcp.acknowledge_event("event-123")

        assert result["success"] is True


class TestEventsMCPClearAlerts:
    """测试 clear_alerts 方法"""

    def test_clear_alerts(self):
        """测试清除告警事件"""
        from ovirt_engine_mcp_server.mcp_events import EventsMCP

        mock_alerts = [
            _create_mock_event("event-1", "Alert 1", "alert"),
            _create_mock_event("event-2", "Alert 2", "alert"),
        ]

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_events_service = MagicMock()
        mock_events_service.list.return_value = mock_alerts
        mock_events_service.event_service.return_value.remove.return_value = None

        mock_ovirt.connection.system_service.return_value.events_service.return_value = mock_events_service

        events_mcp = EventsMCP(mock_ovirt)
        result = events_mcp.clear_alerts()

        assert result["success"] is True
        assert result["cleared_count"] == 2


class TestEventsMCPTools:
    """测试 MCP_TOOLS 注册表"""

    def test_mcp_tools_defined(self):
        """测试 MCP 工具注册表已定义"""
        from ovirt_engine_mcp_server.mcp_events import MCP_TOOLS

        expected_tools = [
            "event_list",
            "event_get",
            "event_search",
            "event_alerts",
            "event_errors",
            "event_warnings",
            "event_summary",
            "event_acknowledge",
            "event_clear_alerts",
        ]

        for tool in expected_tools:
            assert tool in MCP_TOOLS, f"Missing tool: {tool}"
            assert "method" in MCP_TOOLS[tool]
            assert "description" in MCP_TOOLS[tool]
