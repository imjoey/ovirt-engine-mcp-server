#!/usr/bin/env python3
"""
oVirt MCP Server - 系统管理模块
提供系统信息、选项、任务管理等系统级功能
"""
from typing import Dict, List, Any, Optional
import logging

try:
    import ovirtsdk4 as sdk
except ImportError:
    sdk = None

logger = logging.getLogger(__name__)


class SystemMCP:
    """系统管理 MCP"""

    def __init__(self, ovirt_mcp):
        self.ovirt = ovirt_mcp

    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息

        Returns:
            系统信息
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        try:
            system_service = self.ovirt.connection.system_service()
            api = system_service.get()

            # 获取版本信息
            version = {
                "major": api.product_info.version.major if api.product_info and api.product_info.version else 0,
                "minor": api.product_info.version.minor if api.product_info and api.product_info.version else 0,
                "build": api.product_info.version.build if api.product_info and api.product_info.version else 0,
                "revision": api.product_info.version.revision if api.product_info and api.product_info.version else "",
                "full_version": f"{api.product_info.version.major}.{api.product_info.version.minor}.{api.product_info.version.build}" if api.product_info and api.product_info.version else "unknown",
            }

            # 获取统计信息
            summary = {}
            try:
                summary_response = system_service.get_summary()
                if summary_response:
                    summary = {
                        "vms": {
                            "total": summary_response.vms.total if summary_response.vms else 0,
                            "active": summary_response.vms.active if summary_response.vms else 0,
                        },
                        "hosts": {
                            "total": summary_response.hosts.total if summary_response.hosts else 0,
                            "active": summary_response.hosts.active if summary_response.hosts else 0,
                        },
                        "storage_domains": {
                            "total": summary_response.storage_domains.total if summary_response.storage_domains else 0,
                            "active": summary_response.storage_domains.active if summary_response.storage_domains else 0,
                        },
                        "users": {
                            "total": summary_response.users.total if summary_response.users else 0,
                        },
                    }
            except Exception as e:
                logger.debug(f"获取统计信息失败: {e}")

            return {
                "product_name": api.product_info.name if api.product_info else "",
                "vendor_name": api.product_info.vendor if api.product_info else "",
                "version": version,
                "summary": summary,
                "time_zone": str(api.time_zone.name) if api.time_zone else "",
                "time": str(api.time) if hasattr(api, 'time') else "",
                "user": {
                    "name": api.user_name if hasattr(api, 'user_name') else "",
                },
            }
        except Exception as e:
            raise RuntimeError(f"获取系统信息失败: {e}")

    def list_system_options(self, category: str = None) -> List[Dict]:
        """列出系统选项

        Args:
            category: 选项分类（可选）

        Returns:
            系统选项列表
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        try:
            system_service = self.ovirt.connection.system_service()
            options_service = system_service.system_options_service()

            if category:
                options = options_service.list(filter=f"category={category}")
            else:
                options = options_service.list()

        except Exception as e:
            logger.error(f"获取系统选项失败: {e}")
            return []

        return [
            {
                "id": o.id,
                "name": o.name if hasattr(o, 'name') else "",
                "value": o.value if hasattr(o, 'value') else "",
                "type": str(o.type.value) if hasattr(o, 'type') and o.type else "",
                "description": o.description if hasattr(o, 'description') else "",
            }
            for o in options
        ]

    # ── 任务管理 ────────────────────────────────────────────────────────────

    def list_jobs(self, page: int = 1, page_size: int = 50) -> List[Dict]:
        """列出任务

        Args:
            page: 页码
            page_size: 每页数量

        Returns:
            任务列表
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        try:
            jobs_service = self.ovirt.connection.system_service().jobs_service()
            jobs = jobs_service.list(max=page * page_size)

            # 分页
            start_idx = (page - 1) * page_size
            jobs = jobs[start_idx:start_idx + page_size]

        except Exception as e:
            logger.error(f"获取任务列表失败: {e}")
            return []

        return [
            {
                "id": j.id,
                "description": j.description if hasattr(j, 'description') else "",
                "status": str(j.status.value) if j.status else "pending",
                "start_time": str(j.start_time) if hasattr(j, 'start_time') else "",
                "end_time": str(j.end_time) if hasattr(j, 'end_time') else "",
                "user": j.owner.name if hasattr(j, 'owner') and j.owner else "",
                "progress": j.progress if hasattr(j, 'progress') else 0,
                "job_type": str(j.job_type.value) if hasattr(j, 'job_type') and j.job_type else "",
            }
            for j in jobs
        ]

    def get_job(self, job_id: str) -> Optional[Dict]:
        """获取任务详情

        Args:
            job_id: 任务 ID

        Returns:
            任务详情
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        try:
            jobs_service = self.ovirt.connection.system_service().jobs_service()
            job = jobs_service.job_service(job_id).get()

            # 获取任务步骤
            steps = []
            try:
                steps_service = jobs_service.job_service(job_id).steps_service()
                step_list = steps_service.list()
                steps = [
                    {
                        "id": s.id,
                        "description": s.description if hasattr(s, 'description') else "",
                        "status": str(s.status.value) if s.status else "",
                        "start_time": str(s.start_time) if hasattr(s, 'start_time') else "",
                        "end_time": str(s.end_time) if hasattr(s, 'end_time') else "",
                        "progress": s.progress if hasattr(s, 'progress') else 0,
                        "type": str(s.type.value) if hasattr(s, 'type') and s.type else "",
                    }
                    for s in step_list
                ]
            except Exception as e:
                logger.debug(f"获取任务步骤失败: {e}")

            return {
                "id": job.id,
                "description": job.description if hasattr(job, 'description') else "",
                "status": str(job.status.value) if job.status else "pending",
                "start_time": str(job.start_time) if hasattr(job, 'start_time') else "",
                "end_time": str(job.end_time) if hasattr(job, 'end_time') else "",
                "user": job.owner.name if hasattr(job, 'owner') and job.owner else "",
                "user_id": job.owner.id if hasattr(job, 'owner') and job.owner else "",
                "progress": job.progress if hasattr(job, 'progress') else 0,
                "job_type": str(job.job_type.value) if hasattr(job, 'job_type') and job.job_type else "",
                "external": job.external if hasattr(job, 'external') else False,
                "auto_cleared": job.auto_cleared if hasattr(job, 'auto_cleared') else False,
                "steps": steps,
                "step_count": len(steps),
            }
        except Exception as e:
            logger.debug(f"获取任务失败: {e}")
            return None

    def cancel_job(self, job_id: str, force: bool = False) -> Dict[str, Any]:
        """取消任务

        Args:
            job_id: 任务 ID
            force: 强制取消

        Returns:
            取消结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        try:
            jobs_service = self.ovirt.connection.system_service().jobs_service()
            job_service = jobs_service.job_service(job_id)

            job_service.cancel(force=force)

            return {
                "success": True,
                "message": f"任务 {job_id} 已取消",
                "job_id": job_id,
            }
        except Exception as e:
            raise RuntimeError(f"取消任务失败: {e}")

    # ── 系统统计 ────────────────────────────────────────────────────────────

    def get_system_statistics(self) -> Dict[str, Any]:
        """获取系统统计信息

        Returns:
            系统统计信息
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        try:
            system_service = self.ovirt.connection.system_service()
            statistics_service = system_service.statistics_service()

            stats = statistics_service.list()

            result = {}
            stat_mapping = {
                "vms": "vms",
                "hosts": "hosts",
                "storage_domains": "storage_domains",
                "data_centers": "data_centers",
                "clusters": "clusters",
                "networks": "networks",
                "templates": "templates",
                "users": "users",
                "events": "events",
            }

            for stat in stats:
                stat_name = stat.name
                if stat_name in stat_mapping:
                    key = stat_mapping[stat_name]
                    if stat.values:
                        value = stat.values[0]
                        if hasattr(value, "datum"):
                            result[key] = value.datum
                        else:
                            result[key] = value
                    else:
                        result[key] = stat.value

            return {
                "statistics": result,
                "total_stats": len(stats),
            }
        except Exception as e:
            logger.error(f"获取系统统计失败: {e}")
            return {"statistics": {}, "error": str(e)}


# MCP 工具注册表
MCP_TOOLS = {
    "system_get": {"method": "get_system_info", "description": "获取系统信息"},
    "system_option_list": {"method": "list_system_options", "description": "列出系统选项"},
    "job_list": {"method": "list_jobs", "description": "列出任务"},
    "job_get": {"method": "get_job", "description": "获取任务详情"},
    "job_cancel": {"method": "cancel_job", "description": "取消任务"},
    "system_statistics": {"method": "get_system_statistics", "description": "获取系统统计信息"},
}
