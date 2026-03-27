#!/usr/bin/env python3
"""
oVirt MCP Server - RBAC 管理模块
提供用户、组、角色、权限、标签的管理功能
"""
from typing import Dict, List, Any, Optional
import logging

from .base_mcp import BaseMCP
from .decorators import require_connection
from .search_utils import sanitize_search_value as _sanitize_search_value

try:
    import ovirtsdk4 as sdk
except ImportError:
    sdk = None

logger = logging.getLogger(__name__)


class RbacMCP(BaseMCP):
    """RBAC 管理 MCP"""

    def __init__(self, ovirt_mcp):
        super().__init__(ovirt_mcp)

    # ── 资源查找辅助方法（BaseMCP 未提供的）───────────────────────────────

    def _find_group(self, name_or_id: str) -> Optional[Any]:
        """查找组（按名称或 ID）"""
        groups_service = self.connection.system_service().groups_service()

        # 先尝试按 ID 查找
        try:
            group = groups_service.group_service(name_or_id).get()
            if group:
                return group
        except Exception:
            pass

        # 按名称搜索
        groups = groups_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return groups[0] if groups else None

    def _find_tag(self, name_or_id: str) -> Optional[Any]:
        """查找标签（按名称或 ID）"""
        tags_service = self.connection.system_service().tags_service()

        # 先尝试按 ID 查找
        try:
            tag = tags_service.tag_service(name_or_id).get()
            if tag:
                return tag
        except Exception:
            pass

        # 按名称搜索
        tags = tags_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return tags[0] if tags else None

    def _get_resource_service(self, resource_type: str, resource_id: str) -> Optional[Any]:
        """根据资源类型获取对应的 service

        Args:
            resource_type: 资源类型（vm, host, cluster, datacenter, network, storagedomain, template）
            resource_id: 资源 ID

        Returns:
            资源对应的 service 对象
        """
        system_service = self.connection.system_service()
        resource_type_lower = resource_type.lower()

        service_map = {
            "vm": lambda: system_service.vms_service().vm_service(resource_id),
            "host": lambda: system_service.hosts_service().host_service(resource_id),
            "cluster": lambda: system_service.clusters_service().cluster_service(resource_id),
            "datacenter": lambda: system_service.data_centers_service().data_center_service(resource_id),
            "network": lambda: system_service.networks_service().network_service(resource_id),
            "storagedomain": lambda: system_service.storage_domains_service().storage_domain_service(resource_id),
            "template": lambda: system_service.templates_service().template_service(resource_id),
        }

        if resource_type_lower not in service_map:
            raise ValueError(f"不支持的资源类型: {resource_type}，支持的类型: {list(service_map.keys())}")

        return service_map[resource_type_lower]()

    def _find_resource_by_type(self, resource_type: str, name_or_id: str) -> Optional[Any]:
        """根据资源类型查找资源"""
        resource_type_lower = resource_type.lower()

        # 定义每种资源类型的查找逻辑
        find_map = {
            "vm": lambda: self._find_vm(name_or_id),
            "host": lambda: self._find_host(name_or_id),
            "cluster": lambda: self._find_cluster(name_or_id),
            "datacenter": lambda: self._find_datacenter(name_or_id),
            "network": lambda: self._find_network(name_or_id),
            "storagedomain": lambda: self._find_storage_domain(name_or_id),
            "template": lambda: self._find_template(name_or_id),
        }

        if resource_type_lower not in find_map:
            raise ValueError(f"不支持的资源类型: {resource_type}")

        return find_map[resource_type_lower]()

    # ── User 管理 ──────────────────────────────────────────────────────────

    @require_connection
    def list_users(self, search: str = None) -> List[Dict]:
        """列出用户

        Args:
            search: 搜索条件（可选）

        Returns:
            用户列表
        """
        users_service = self.connection.system_service().users_service()

        try:
            if search:
                users = users_service.list(search=_sanitize_search_value(search))
            else:
                users = users_service.list()
        except Exception as e:
            logger.error(f"获取用户列表失败: {e}")
            return []

        result = []
        for user in users:
            result.append({
                "id": user.id,
                "name": user.name,
                "user_name": user.user_name,
                "principal": user.principal,
                "email": user.email if hasattr(user, 'email') else "",
                "domain": user.domain.name if user.domain else "",
                "department": user.department if hasattr(user, 'department') else "",
            })

        return result

    @require_connection
    def get_user(self, name_or_id: str) -> Optional[Dict]:
        """获取用户详情

        Args:
            name_or_id: 用户名称或 ID

        Returns:
            用户详情
        """
        user = self._find_user(name_or_id)
        if not user:
            return None

        # 获取用户的权限列表
        permissions = []
        try:
            user_service = self.connection.system_service().users_service().user_service(user.id)
            perms_service = user_service.permissions_service()
            perms = perms_service.list()
            permissions = [
                {
                    "id": p.id,
                    "role": p.role.name if p.role else "",
                    "object_id": p.object.id if p.object else "",
                    "object_type": p.object.type if p.object and hasattr(p.object, 'type') else "",
                }
                for p in perms[:20]  # 限制数量
            ]
        except Exception as e:
            logger.debug(f"获取用户权限失败: {e}")

        return {
            "id": user.id,
            "name": user.name,
            "user_name": user.user_name,
            "principal": user.principal,
            "email": user.email if hasattr(user, 'email') else "",
            "domain": user.domain.name if user.domain else "",
            "department": user.department if hasattr(user, 'department') else "",
            "permissions": permissions,
            "permission_count": len(permissions),
        }

    # ── Group 管理 ─────────────────────────────────────────────────────────

    @require_connection
    def list_groups(self, search: str = None) -> List[Dict]:
        """列出用户组

        Args:
            search: 搜索条件（可选）

        Returns:
            用户组列表
        """
        groups_service = self.connection.system_service().groups_service()

        try:
            if search:
                groups = groups_service.list(search=_sanitize_search_value(search))
            else:
                groups = groups_service.list()
        except Exception as e:
            logger.error(f"获取用户组列表失败: {e}")
            return []

        result = []
        for group in groups:
            result.append({
                "id": group.id,
                "name": group.name,
                "domain": group.domain.name if group.domain else "",
            })

        return result

    @require_connection
    def get_group(self, name_or_id: str) -> Optional[Dict]:
        """获取用户组详情

        Args:
            name_or_id: 组名称或 ID

        Returns:
            用户组详情
        """
        group = self._find_group(name_or_id)
        if not group:
            return None

        # 获取组的权限列表
        permissions = []
        try:
            group_service = self.connection.system_service().groups_service().group_service(group.id)
            perms_service = group_service.permissions_service()
            perms = perms_service.list()
            permissions = [
                {
                    "id": p.id,
                    "role": p.role.name if p.role else "",
                    "object_id": p.object.id if p.object else "",
                    "object_type": p.object.type if p.object and hasattr(p.object, 'type') else "",
                }
                for p in perms[:20]  # 限制数量
            ]
        except Exception as e:
            logger.debug(f"获取组权限失败: {e}")

        return {
            "id": group.id,
            "name": group.name,
            "domain": group.domain.name if group.domain else "",
            "permissions": permissions,
            "permission_count": len(permissions),
        }

    # ── Role 管理 ──────────────────────────────────────────────────────────

    @require_connection
    def list_roles(self) -> List[Dict]:
        """列出所有角色

        Returns:
            角色列表
        """
        roles_service = self.connection.system_service().roles_service()

        try:
            roles = roles_service.list()
        except Exception as e:
            logger.error(f"获取角色列表失败: {e}")
            return []

        result = []
        for role in roles:
            result.append({
                "id": role.id,
                "name": role.name,
                "description": role.description or "",
                "administrative": role.administrative if hasattr(role, 'administrative') else False,
            })

        return result

    @require_connection
    def get_role(self, name_or_id: str) -> Optional[Dict]:
        """获取角色详情（包含权限列表）

        Args:
            name_or_id: 角色名称或 ID

        Returns:
            角色详情
        """
        role = self._find_role(name_or_id)
        if not role:
            return None

        # 获取角色的权限列表（permits）
        permits = []
        try:
            role_service = self.connection.system_service().roles_service().role_service(role.id)
            permits_service = role_service.permits_service()
            permit_list = permits_service.list()
            permits = [
                {
                    "id": p.id,
                    "name": p.name,
                    "administrative": p.administrative if hasattr(p, 'administrative') else False,
                }
                for p in permit_list
            ]
        except Exception as e:
            logger.debug(f"获取角色权限列表失败: {e}")

        return {
            "id": role.id,
            "name": role.name,
            "description": role.description or "",
            "administrative": role.administrative if hasattr(role, 'administrative') else False,
            "permits": permits,
            "permit_count": len(permits),
        }

    @require_connection
    def create_role(self, name: str, description: str = "",
                   administrative: bool = False,
                   permit_ids: List[str] = None) -> Dict[str, Any]:
        """创建角色

        Args:
            name: 角色名称
            description: 描述
            administrative: 是否为管理员角色
            permit_ids: 权限 ID 列表

        Returns:
            创建结果
        """
        roles_service = self.connection.system_service().roles_service()

        # 检查是否已存在
        existing = roles_service.list(search=f"name={_sanitize_search_value(name)}")
        if existing:
            raise ValueError(f"角色已存在: {name}")

        # 构建 permit 列表
        permits = []
        if permit_ids:
            for permit_id in permit_ids:
                permits.append(sdk.types.Permit(id=permit_id))

        try:
            role = roles_service.add(
                sdk.types.Role(
                    name=name,
                    description=description,
                    administrative=administrative,
                    permits=permits if permits else None,
                )
            )

            return {
                "success": True,
                "message": f"角色 {name} 已创建",
                "role_id": role.id,
            }
        except Exception as e:
            raise RuntimeError(f"创建角色失败: {e}")

    @require_connection
    def delete_role(self, name_or_id: str) -> Dict[str, Any]:
        """删除角色

        Args:
            name_or_id: 角色名称或 ID

        Returns:
            删除结果
        """
        role = self._find_role(name_or_id)
        if not role:
            raise ValueError(f"角色不存在: {name_or_id}")

        # 检查是否为系统内置角色
        if hasattr(role, 'administrative') and role.id in ['00000000-0000-0000-0000-000000000001',
                                                            '00000000-0000-0000-0000-000000000002']:
            raise ValueError("不能删除系统内置角色")

        roles_service = self.connection.system_service().roles_service()
        role_service = roles_service.role_service(role.id)

        try:
            role_service.remove()
            return {"success": True, "message": f"角色 {role.name} 已删除"}
        except Exception as e:
            raise RuntimeError(f"删除角色失败: {e}")

    # ── Permit 管理 ────────────────────────────────────────────────────────

    @require_connection
    def list_permits(self) -> List[Dict]:
        """列出所有权限单元

        Returns:
            权限单元列表
        """
        # 通过获取所有角色的 permits 来汇总
        permits_map = {}  # 用 id 去重

        try:
            roles_service = self.connection.system_service().roles_service()
            roles = roles_service.list()

            for role in roles:
                try:
                    role_service = roles_service.role_service(role.id)
                    permits_service = role_service.permits_service()
                    permit_list = permits_service.list()

                    for p in permit_list:
                        if p.id not in permits_map:
                            permits_map[p.id] = {
                                "id": p.id,
                                "name": p.name,
                                "administrative": p.administrative if hasattr(p, 'administrative') else False,
                            }
                except Exception as e:
                    logger.debug(f"获取角色 {role.name} 的权限失败: {e}")

        except Exception as e:
            logger.error(f"获取权限列表失败: {e}")
            return []

        return list(permits_map.values())

    # ── Permission 管理 ────────────────────────────────────────────────────

    @require_connection
    def list_permissions(self, resource_type: str, resource_id: str) -> List[Dict]:
        """列出资源的权限

        Args:
            resource_type: 资源类型（vm, host, cluster, datacenter, network, storagedomain, template）
            resource_id: 资源 ID

        Returns:
            权限列表
        """
        # 先查找资源
        resource = self._find_resource_by_type(resource_type, resource_id)
        if not resource:
            raise ValueError(f"资源不存在: {resource_type}/{resource_id}")

        # 获取资源的 permissions_service
        resource_service = self._get_resource_service(resource_type, resource.id)
        permissions_service = resource_service.permissions_service()

        try:
            permissions = permissions_service.list()
        except Exception as e:
            logger.error(f"获取权限列表失败: {e}")
            return []

        result = []
        for perm in permissions:
            result.append({
                "id": perm.id,
                "role": perm.role.name if perm.role else "",
                "role_id": perm.role.id if perm.role else "",
                "user": perm.user.name if perm.user else "",
                "user_id": perm.user.id if perm.user else "",
                "group": perm.group.name if perm.group else "",
                "group_id": perm.group.id if perm.group else "",
            })

        return result

    @require_connection
    def assign_permission(self, resource_type: str, resource_id: str,
                         user_or_group: str, role_name: str,
                         principal_name: str) -> Dict[str, Any]:
        """分配权限

        Args:
            resource_type: 资源类型（vm, host, cluster, datacenter, network, storagedomain, template）
            resource_id: 资源 ID 或名称
            user_or_group: 主体类型（user 或 group）
            role_name: 角色名称或 ID
            principal_name: 用户名或组名

        Returns:
            分配结果
        """
        # 验证参数
        if user_or_group.lower() not in ["user", "group"]:
            raise ValueError("user_or_group 必须是 'user' 或 'group'")

        # 查找资源
        resource = self._find_resource_by_type(resource_type, resource_id)
        if not resource:
            raise ValueError(f"资源不存在: {resource_type}/{resource_id}")

        # 查找角色
        role = self._find_role(role_name)
        if not role:
            raise ValueError(f"角色不存在: {role_name}")

        # 查找用户或组
        user_obj = None
        group_obj = None

        if user_or_group.lower() == "user":
            user_obj = self._find_user(principal_name)
            if not user_obj:
                raise ValueError(f"用户不存在: {principal_name}")
        else:
            group_obj = self._find_group(principal_name)
            if not group_obj:
                raise ValueError(f"组不存在: {principal_name}")

        # 获取资源的 permissions_service
        resource_service = self._get_resource_service(resource_type, resource.id)
        permissions_service = resource_service.permissions_service()

        # 构建权限对象
        try:
            if user_obj:
                permission = sdk.types.Permission(
                    user=sdk.types.User(id=user_obj.id),
                    role=sdk.types.Role(id=role.id),
                )
            else:
                permission = sdk.types.Permission(
                    group=sdk.types.Group(id=group_obj.id),
                    role=sdk.types.Role(id=role.id),
                )

            result = permissions_service.add(permission)

            return {
                "success": True,
                "message": f"已将角色 {role.name} 分配给 {user_or_group} {principal_name}",
                "permission_id": result.id,
                "resource_type": resource_type,
                "resource_id": resource.id,
                "role": role.name,
            }
        except Exception as e:
            raise RuntimeError(f"分配权限失败: {e}")

    @require_connection
    def revoke_permission(self, resource_type: str, resource_id: str,
                         permission_id: str) -> Dict[str, Any]:
        """撤销权限

        Args:
            resource_type: 资源类型
            resource_id: 资源 ID 或名称
            permission_id: 权限 ID

        Returns:
            撤销结果
        """
        # 查找资源
        resource = self._find_resource_by_type(resource_type, resource_id)
        if not resource:
            raise ValueError(f"资源不存在: {resource_type}/{resource_id}")

        # 获取资源的 permissions_service
        resource_service = self._get_resource_service(resource_type, resource.id)
        permissions_service = resource_service.permissions_service()
        permission_service = permissions_service.permission_service(permission_id)

        try:
            permission_service.remove()
            return {"success": True, "message": f"权限 {permission_id} 已撤销"}
        except Exception as e:
            raise RuntimeError(f"撤销权限失败: {e}")

    # ── Tag 管理 ───────────────────────────────────────────────────────────

    @require_connection
    def list_tags(self) -> List[Dict]:
        """列出所有标签

        Returns:
            标签列表
        """
        tags_service = self.connection.system_service().tags_service()

        try:
            tags = tags_service.list()
        except Exception as e:
            logger.error(f"获取标签列表失败: {e}")
            return []

        result = []
        for tag in tags:
            result.append({
                "id": tag.id,
                "name": tag.name,
                "description": tag.description or "",
                "parent_id": tag.parent.id if tag.parent else "",
            })

        return result

    @require_connection
    def create_tag(self, name: str, description: str = "",
                  parent_name: str = None) -> Dict[str, Any]:
        """创建标签

        Args:
            name: 标签名称
            description: 描述
            parent_name: 父标签名称（可选）

        Returns:
            创建结果
        """
        tags_service = self.connection.system_service().tags_service()

        # 检查是否已存在
        existing = tags_service.list(search=f"name={_sanitize_search_value(name)}")
        if existing:
            raise ValueError(f"标签已存在: {name}")

        # 构建标签对象
        parent_tag = None
        if parent_name:
            parent = self._find_tag(parent_name)
            if not parent:
                raise ValueError(f"父标签不存在: {parent_name}")
            parent_tag = sdk.types.Tag(id=parent.id)

        try:
            tag = tags_service.add(
                sdk.types.Tag(
                    name=name,
                    description=description,
                    parent=parent_tag,
                )
            )

            return {
                "success": True,
                "message": f"标签 {name} 已创建",
                "tag_id": tag.id,
            }
        except Exception as e:
            raise RuntimeError(f"创建标签失败: {e}")

    @require_connection
    def delete_tag(self, name_or_id: str) -> Dict[str, Any]:
        """删除标签

        Args:
            name_or_id: 标签名称或 ID

        Returns:
            删除结果
        """
        tag = self._find_tag(name_or_id)
        if not tag:
            raise ValueError(f"标签不存在: {name_or_id}")

        tags_service = self.connection.system_service().tags_service()
        tag_service = tags_service.tag_service(tag.id)

        try:
            tag_service.remove()
            return {"success": True, "message": f"标签 {tag.name} 已删除"}
        except Exception as e:
            raise RuntimeError(f"删除标签失败: {e}")

    @require_connection
    def assign_tag(self, resource_type: str, resource_id: str,
                  tag_name: str) -> Dict[str, Any]:
        """为资源分配标签

        Args:
            resource_type: 资源类型（vm, host, cluster, datacenter, network, storagedomain, template）
            resource_id: 资源 ID 或名称
            tag_name: 标签名称或 ID

        Returns:
            分配结果
        """
        # 查找资源
        resource = self._find_resource_by_type(resource_type, resource_id)
        if not resource:
            raise ValueError(f"资源不存在: {resource_type}/{resource_id}")

        # 查找标签
        tag = self._find_tag(tag_name)
        if not tag:
            raise ValueError(f"标签不存在: {tag_name}")

        # 获取资源的 tags_service
        resource_service = self._get_resource_service(resource_type, resource.id)
        tags_service = resource_service.tags_service()

        # 检查是否已分配
        try:
            existing_tags = tags_service.list()
            for existing in existing_tags:
                if existing.id == tag.id:
                    return {"success": True, "message": f"标签 {tag.name} 已分配给资源"}
        except Exception:
            pass

        # 分配标签
        try:
            tags_service.add(sdk.types.Tag(id=tag.id))

            return {
                "success": True,
                "message": f"标签 {tag.name} 已分配给 {resource_type}",
                "tag_id": tag.id,
                "resource_type": resource_type,
                "resource_id": resource.id,
            }
        except Exception as e:
            raise RuntimeError(f"分配标签失败: {e}")

    @require_connection
    def unassign_tag(self, resource_type: str, resource_id: str,
                    tag_name: str) -> Dict[str, Any]:
        """移除资源的标签

        Args:
            resource_type: 资源类型
            resource_id: 资源 ID 或名称
            tag_name: 标签名称或 ID

        Returns:
            移除结果
        """
        # 查找资源
        resource = self._find_resource_by_type(resource_type, resource_id)
        if not resource:
            raise ValueError(f"资源不存在: {resource_type}/{resource_id}")

        # 查找标签
        tag = self._find_tag(tag_name)
        if not tag:
            raise ValueError(f"标签不存在: {tag_name}")

        # 获取资源的 tags_service
        resource_service = self._get_resource_service(resource_type, resource.id)
        tags_service = resource_service.tags_service()
        tag_service = tags_service.tag_service(tag.id)

        try:
            tag_service.remove()
            return {"success": True, "message": f"标签 {tag.name} 已从资源移除"}
        except Exception as e:
            raise RuntimeError(f"移除标签失败: {e}")

    @require_connection
    def list_resource_tags(self, resource_type: str, resource_id: str) -> List[Dict]:
        """列出资源的标签

        Args:
            resource_type: 资源类型
            resource_id: 资源 ID 或名称

        Returns:
            标签列表
        """
        # 查找资源
        resource = self._find_resource_by_type(resource_type, resource_id)
        if not resource:
            raise ValueError(f"资源不存在: {resource_type}/{resource_id}")

        # 获取资源的 tags_service
        resource_service = self._get_resource_service(resource_type, resource.id)
        tags_service = resource_service.tags_service()

        try:
            tags = tags_service.list()
        except Exception as e:
            logger.error(f"获取资源标签失败: {e}")
            return []

        result = []
        for tag in tags:
            result.append({
                "id": tag.id,
                "name": tag.name,
                "description": tag.description or "",
            })

        return result

    # ── User 扩展管理 ────────────────────────────────────────────────────────

    @require_connection
    def create_user(self, user_name: str, domain: str,
                   email: str = None, department: str = None) -> Dict[str, Any]:
        """创建用户

        Args:
            user_name: 用户名（格式：user@domain）
            domain: 域名称
            email: 邮箱地址
            department: 部门

        Returns:
            创建结果
        """
        users_service = self.connection.system_service().users_service()

        # 查找域
        domains_service = self.connection.system_service().domains_service()
        domains = domains_service.list(search=f"name={_sanitize_search_value(domain)}")
        if not domains:
            raise ValueError(f"域不存在: {domain}")

        try:
            user = users_service.add(
                sdk.types.User(
                    user_name=user_name,
                    domain=sdk.types.Domain(id=domains[0].id),
                    email=email,
                    department=department,
                )
            )

            return {
                "success": True,
                "message": f"用户 {user_name} 已创建",
                "user_id": user.id,
            }
        except Exception as e:
            raise RuntimeError(f"创建用户失败: {e}")

    @require_connection
    def update_user(self, name_or_id: str, email: str = None,
                   department: str = None) -> Dict[str, Any]:
        """更新用户

        Args:
            name_or_id: 用户名称或 ID
            email: 新邮箱
            department: 新部门

        Returns:
            更新结果
        """
        user = self._find_user(name_or_id)
        if not user:
            raise ValueError(f"用户不存在: {name_or_id}")

        users_service = self.connection.system_service().users_service()
        user_service = users_service.user_service(user.id)

        if email is not None:
            user.email = email
        if department is not None:
            user.department = department

        try:
            user_service.update(user)
            return {"success": True, "message": f"用户已更新"}
        except Exception as e:
            raise RuntimeError(f"更新用户失败: {e}")

    @require_connection
    def delete_user(self, name_or_id: str) -> Dict[str, Any]:
        """删除用户

        Args:
            name_or_id: 用户名称或 ID

        Returns:
            删除结果
        """
        user = self._find_user(name_or_id)
        if not user:
            raise ValueError(f"用户不存在: {name_or_id}")

        users_service = self.connection.system_service().users_service()
        user_service = users_service.user_service(user.id)

        try:
            user_service.remove()
            return {"success": True, "message": f"用户 {user.name} 已删除"}
        except Exception as e:
            raise RuntimeError(f"删除用户失败: {e}")

    @require_connection
    def list_user_groups(self, name_or_id: str) -> List[Dict]:
        """列出用户所属的组

        Args:
            name_or_id: 用户名称或 ID

        Returns:
            组列表
        """
        user = self._find_user(name_or_id)
        if not user:
            raise ValueError(f"用户不存在: {name_or_id}")

        users_service = self.connection.system_service().users_service()
        user_service = users_service.user_service(user.id)
        groups_service = user_service.groups_service()

        try:
            groups = groups_service.list()
        except Exception as e:
            logger.error(f"获取用户组失败: {e}")
            return []

        return [
            {
                "id": g.id,
                "name": g.name,
                "domain": g.domain.name if g.domain else "",
            }
            for g in groups
        ]

    # ── Role 扩展管理 ────────────────────────────────────────────────────────

    @require_connection
    def update_role(self, name_or_id: str, new_name: str = None,
                   description: str = None,
                   administrative: bool = None) -> Dict[str, Any]:
        """更新角色

        Args:
            name_or_id: 角色名称或 ID
            new_name: 新名称
            description: 新描述
            administrative: 是否为管理员角色

        Returns:
            更新结果
        """
        role = self._find_role(name_or_id)
        if not role:
            raise ValueError(f"角色不存在: {name_or_id}")

        roles_service = self.connection.system_service().roles_service()
        role_service = roles_service.role_service(role.id)

        if new_name:
            role.name = new_name
        if description is not None:
            role.description = description
        if administrative is not None:
            role.administrative = administrative

        try:
            role_service.update(role)
            return {"success": True, "message": f"角色已更新"}
        except Exception as e:
            raise RuntimeError(f"更新角色失败: {e}")

    # ── Filter 管理 ──────────────────────────────────────────────────────────

    @require_connection
    def list_filters(self) -> List[Dict]:
        """列出权限过滤器

        Returns:
            过滤器列表
        """
        filters_service = self.connection.system_service().filters_service()

        try:
            filters = filters_service.list()
        except Exception as e:
            logger.error(f"获取过滤器列表失败: {e}")
            return []

        return [
            {
                "id": f.id,
                "name": f.name if hasattr(f, 'name') else "",
                "permission": f.permission.name if hasattr(f, 'permission') and f.permission else "",
            }
            for f in filters
        ]


# MCP 工具注册表
MCP_TOOLS = {
    # User 管理
    "user_list": {"method": "list_users", "description": "列出用户"},
    "user_get": {"method": "get_user", "description": "获取用户详情"},
    "user_create": {"method": "create_user", "description": "创建用户"},
    "user_update": {"method": "update_user", "description": "更新用户"},
    "user_delete": {"method": "delete_user", "description": "删除用户"},
    "user_groups": {"method": "list_user_groups", "description": "列出用户所属的组"},

    # Group 管理
    "group_list": {"method": "list_groups", "description": "列出用户组"},
    "group_get": {"method": "get_group", "description": "获取用户组详情"},

    # Role 管理
    "role_list": {"method": "list_roles", "description": "列出角色"},
    "role_get": {"method": "get_role", "description": "获取角色详情"},
    "role_create": {"method": "create_role", "description": "创建角色"},
    "role_update": {"method": "update_role", "description": "更新角色"},
    "role_delete": {"method": "delete_role", "description": "删除角色"},

    # Permit 管理
    "permit_list": {"method": "list_permits", "description": "列出所有权限单元"},

    # Permission 管理
    "permission_list": {"method": "list_permissions", "description": "列出资源的权限"},
    "permission_assign": {"method": "assign_permission", "description": "分配权限"},
    "permission_revoke": {"method": "revoke_permission", "description": "撤销权限"},

    # Tag 管理
    "tag_list": {"method": "list_tags", "description": "列出所有标签"},
    "tag_create": {"method": "create_tag", "description": "创建标签"},
    "tag_delete": {"method": "delete_tag", "description": "删除标签"},
    "tag_assign": {"method": "assign_tag", "description": "为资源分配标签"},
    "tag_unassign": {"method": "unassign_tag", "description": "移除资源的标签"},
    "tag_list_resources": {"method": "list_resource_tags", "description": "列出资源的标签"},

    # Filter 管理
    "filter_list": {"method": "list_filters", "description": "列出权限过滤器"},
}
