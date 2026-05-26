import os
import yaml
import re
from typing import List, Dict, Set
from logger.unified_logger import app_logger, error_logger

class PermissionValidator:
    """
    Utility for loading, caching, and validating user permissions
    based on the machine-readable config/permissions.yaml matrix.
    Supports role hierarchy inheritance and wildcard (*:*) checks.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PermissionValidator, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: str = "config/permissions.yaml"):
        if self._initialized:
            return
        
        self.config_path = config_path
        self.roles_config: Dict[str, dict] = {}
        self.protected_routes: Dict[str, str] = {}
        self.role_expanded_permissions: Dict[str, Set[str]] = {}
        self._load_config()
        self._expand_all_roles()
        self._initialized = True

    def _load_config(self):
        """Loads and parses the permissions.yaml file."""
        if not os.path.exists(self.config_path):
            app_logger.warning(f"Permissions config not found at {self.config_path}, fallback to empty permissions.")
            return

        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)
                if config:
                    self.roles_config = config.get("roles", {})
                    self.protected_routes = config.get("protected_routes", {})
                    app_logger.info(f"Loaded {len(self.roles_config)} roles and {len(self.protected_routes)} protected routes from permissions.yaml")
        except Exception as e:
            error_logger.error(f"Failed to load permissions configuration: {e}", exc_info=True)

    def _expand_all_roles(self):
        """Expands permissions for all roles based on the inheritance tree."""
        for role in self.roles_config:
            self.role_expanded_permissions[role] = self._expand_role_permissions(role, set())

    def _expand_role_permissions(self, role: str, visited: Set[str]) -> Set[str]:
        """Recursively resolves all permissions for a role, including inheritance."""
        if role in visited:
            # Prevent infinite loops in case of cyclic inheritance
            return set()
        
        visited.add(role)
        role_data = self.roles_config.get(role, {})
        permissions = set(role_data.get("permissions", []))
        
        # Inherit permissions from parent roles
        for parent_role in role_data.get("inherits", []):
            permissions.update(self._expand_role_permissions(parent_role, visited.copy()))
            
        return permissions

    def get_user_permissions(self, user_roles: List[str]) -> Set[str]:
        """Aggregates and returns the complete set of permissions for a list of user roles."""
        expanded = set()
        for role in user_roles:
            if role in self.role_expanded_permissions:
                expanded.update(self.role_expanded_permissions[role])
        return expanded

    def has_permission(self, user_roles: List[str], required_permission: str) -> bool:
        """
        Checks if the user has the required permission.
        Always grants access if the user has wildcard ("*:*") permission.
        """
        user_perms = self.get_user_permissions(user_roles)
        
        # Wildcard permission bypass
        if "*:*" in user_perms:
            return True
            
        return required_permission in user_perms

    def match_route_permission(self, method: str, path: str) -> str | None:
        """
        Matches a request method and path against the protected routes list.
        Returns the required permission string, or None if the route is not protected.
        Supports matching Flask-style path parameters, e.g. <project_id> or <form_id>.
        """
        # Clean path by stripping query parameters
        clean_path = path.split("?")[0]
        request_signature = f"{method.upper()} {clean_path}"

        for route_pattern, val in self.protected_routes.items():
            # Convert Flask-style pattern "GET /api/v1/foo/<id>" to regex pattern
            # replace <parameter> with ([^/]+)
            regex_pattern = "^" + re.sub(r"<[^>]+>", r"[^/]+", route_pattern) + "$"
            if re.match(regex_pattern, request_signature):
                if isinstance(val, dict):
                    return val.get("permission")
                return val

        return None

    def validate_route_access(self, user_roles: List[str], method: str, path: str) -> bool:
        """
        Validates if the user roles have access to the given route.
        If the route is not defined in protected_routes, access is permitted by default.
        """
        required_permission = self.match_route_permission(method, path)
        if not required_permission:
            # Public/unprotected endpoint
            return True
            
        return self.has_permission(user_roles, required_permission)

# Global singleton helper instance
permission_validator = PermissionValidator()
