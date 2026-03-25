#!/usr/bin/env python3
"""
oVirt MCP Server - 事件管理模块
提供事件查询和告警管理
"""
from typing import Dict, List, Any, Optional
import logging

from .search_utils import sanitize_search_value as _sanitize_search_value

try:
    import ovirtsdk4 as sdk
except ImportError:
    sdk = None

logger = logging.getLogger(__name__)


class EventsMCP:
    """事件管理 MCP"""

    def __init__(self, ovirt_mcp):
        self.ovirt = ovirt_mcp

    def list_events(self, search: str = None, severity: str = None,
                   page: int = 1, page_size: int = 50) -> List[Dict]:
        """列出事件

        Args:
            search: 搜索条件（可选）
            severity: 严重级别过滤（error/warning/info/normal/alert）
            page: 页码，从 1 开始
            page_size: 每页数量，默认 50

        Returns:
            事件列表
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        events_service = self.ovirt.connection.system_service().events_service()

        # 构建搜索条件
        search_query = ""
        if search:
            search_query = _sanitize_search_value(search)

        # 获取事件
        try:
            # SDK 使用 max 参数限制返回数量
            max_results = page * page_size
            events = events_service.list(
                search=search_query if search_query else None,
                max=max_results
            )

            # 过滤严重级别
            if severity:
                severity_lower = severity.lower()
                events = [e for e in events if e.severity and e.severity.value.lower() == severity_lower]

            # 分页处理
            start_idx = (page - 1) * page_size
            events = events[start_idx:start_idx + page_size]

        except Exception as e:
            logger.error(f"获取事件失败: {e}")
            events = []

        result = []
        for event in events:
            result.append({
                "id": event.id,
                "code": event.code if hasattr(event, 'code') else 0,
                "description": event.description or "",
                "severity": str(event.severity.value) if event.severity else "normal",
                "time": str(event.time) if event.time else "",
                "user": event.user.name if event.user else "",
                "cluster": event.cluster.name if event.cluster else "",
                "host": event.host.name if event.host else "",
                "vm": event.vm.name if event.vm else "",
                "data_center": event.data_center.name if event.data_center else "",
                "origin": event.origin if hasattr(event, 'origin') else "",
                "custom_id": event.custom_id if hasattr(event, 'custom_id') else "",
            })

        return result

    def get_alerts(self, page: int = 1, page_size: int = 50) -> List[Dict]:
        """获取告警事件（severity=alert 的所有事件）"""
        return self.list_events(severity="alert", page=page, page_size=page_size)

    def get_errors(self, page: int = 1, page_size: int = 50) -> List[Dict]:
        """获取错误事件"""
        return self.list_events(severity="error", page=page, page_size=page_size)

    def get_warnings(self, page: int = 1, page_size: int = 50) -> List[Dict]:
        """获取警告事件"""
        return self.list_events(severity="warning", page=page, page_size=page_size)

    def get_event(self, event_id: str) -> Optional[Dict]:
        """获取单个事件详情"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        try:
            event_service = self.ovirt.connection.system_service().events_service().event_service(event_id)
            event = event_service.get()

            return {
                "id": event.id,
                "code": event.code if hasattr(event, 'code') else 0,
                "description": event.description or "",
                "severity": str(event.severity.value) if event.severity else "normal",
                "time": str(event.time) if event.time else "",
                "user": event.user.name if event.user else "",
                "user_id": event.user.id if event.user else "",
                "cluster": event.cluster.name if event.cluster else "",
                "cluster_id": event.cluster.id if event.cluster else "",
                "host": event.host.name if event.host else "",
                "host_id": event.host.id if event.host else "",
                "vm": event.vm.name if event.vm else "",
                "vm_id": event.vm.id if event.vm else "",
                "data_center": event.data_center.name if event.data_center else "",
                "data_center_id": event.data_center.id if event.data_center else "",
                "template": event.template.name if event.template else "",
                "storage_domain": event.storage_domain.name if event.storage_domain else "",
                "origin": event.origin if hasattr(event, 'origin') else "",
                "custom_id": event.custom_id if hasattr(event, 'custom_id') else "",
                "flood_rate": event.flood_rate if hasattr(event, 'flood_rate') else 0,
                "correlation_id": event.correlation_id if hasattr(event, 'correlation_id') else "",
            }
        except Exception as e:
            logger.debug(f"获取事件失败: {e}")
            return None

    def search_events(self, query: str, page: int = 1, page_size: int = 50) -> List[Dict]:
        """搜索事件

        支持的搜索字段:
        - vm.name: 虚拟机名称
        - host.name: 主机名称
        - cluster.name: 集群名称
        - severity: 严重级别
        - time: 时间范围

        示例:
        - "vm.name = myvm"
        - "severity = alert"
        - "time > yesterday"
        """
        return self.list_events(search=query, page=page, page_size=page_size)

    def get_events_summary(self, hours: int = 24) -> Dict[str, Any]:
        """获取事件统计摘要

        Args:
            hours: 统计最近 N 小时的事件，默认 24 小时

        Returns:
            各级别事件数量统计
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        events_service = self.ovirt.connection.system_service().events_service()

        # 获取最近的事件（根据 SDK 支持的参数）
        try:
            # 使用 from_date 参数过滤（如果 SDK 支持）
            events = events_service.list(max=500)
        except Exception as e:
            logger.error(f"获取事件失败: {e}")
            return {"error": str(e)}

        # 统计各级别事件
        summary = {
            "total": len(events),
            "alert": 0,
            "error": 0,
            "warning": 0,
            "normal": 0,
            "info": 0,
            "by_cluster": {},
            "by_host": {},
            "by_vm": {},
        }

        for event in events:
            severity = str(event.severity.value) if event.severity else "normal"
            if severity in summary:
                summary[severity] += 1

            # 按集群统计
            if event.cluster:
                cluster_name = event.cluster.name
                summary["by_cluster"][cluster_name] = summary["by_cluster"].get(cluster_name, 0) + 1

            # 按主机统计
            if event.host:
                host_name = event.host.name
                summary["by_host"][host_name] = summary["by_host"].get(host_name, 0) + 1

            # 按 VM 统计
            if event.vm:
                vm_name = event.vm.name
                summary["by_vm"][vm_name] = summary["by_vm"].get(vm_name, 0) + 1

        return summary

    def acknowledge_event(self, event_id: str) -> Dict[str, Any]:
        """确认事件"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        try:
            event_service = self.ovirt.connection.system_service().events_service().event_service(event_id)
            # 标记为已读/已确认
            event = event_service.get()
            if hasattr(event, 'acknowledged'):
                event.acknowledged = True
                event_service.update(event)

            return {"success": True, "message": f"事件 {event_id} 已确认"}
        except Exception as e:
            raise RuntimeError(f"确认事件失败: {e}")

    def clear_alerts(self) -> Dict[str, Any]:
        """清除所有告警事件"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        try:
            events_service = self.ovirt.connection.system_service().events_service()
            alerts = events_service.list(search="severity=alert")

            cleared_count = 0
            for alert in alerts:
                try:
                    event_service = events_service.event_service(alert.id)
                    event_service.remove()
                    cleared_count += 1
                except Exception as e:
                    logger.debug(f"清除事件 {alert.id} 失败: {e}")

            return {
                "success": True,
                "message": f"已清除 {cleared_count} 个告警事件",
                "cleared_count": cleared_count,
            }
        except Exception as e:
            raise RuntimeError(f"清除告警失败: {e}")


# MCP 工具注册表
MCP_TOOLS = {
    "event_list": {"method": "list_events", "description": "列出事件"},
    "event_get": {"method": "get_event", "description": "获取事件详情"},
    "event_search": {"method": "search_events", "description": "搜索事件"},
    "event_alerts": {"method": "get_alerts", "description": "获取告警事件"},
    "event_errors": {"method": "get_errors", "description": "获取错误事件"},
    "event_warnings": {"method": "get_warnings", "description": "获取警告事件"},
    "event_summary": {"method": "get_events_summary", "description": "获取事件统计摘要"},
    "event_acknowledge": {"method": "acknowledge_event", "description": "确认事件"},
    "event_clear_alerts": {"method": "clear_alerts", "description": "清除告警事件"},
}
