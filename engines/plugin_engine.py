"""
engines/plugin_engine.py
Plugin engine for loading, executing, and managing plugins with sandbox security.
Provides a secure environment for plugin execution with proper permission isolation.
"""

import importlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Type
from pathlib import Path
import hashlib

from models.plugin import Plugin, PluginVersion, ComponentSchema
from models.base import BaseDocument
from utils.exceptions import PluginError, SecurityError, ValidationError
from logger.unified_logger import audit_logger, app_logger

logger = logging.getLogger(__name__)


class PluginSandbox:
    """
    Secure sandbox for executing plugin code with restricted permissions.
    """
    
    def __init__(self, plugin_id: str, permissions: List[str]):
        self.plugin_id = plugin_id
        self.permissions = permissions
        self._validate_permissions()
        
    def _validate_permissions(self):
        """Validate that requested permissions are allowed."""
        allowed_permissions = {
            'db_read_own_org',
            'db_write_own_org', 
            'internet_access',
            'filesystem_read',
            'filesystem_write'
        }
        
        for perm in self.permissions:
            if perm not in allowed_permissions:
                raise SecurityError(f"Permission not allowed: {perm}")
    
    def execute(self, code_path: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute plugin code in a secure sandbox environment.
        
        Args:
            code_path: Path to the plugin code file
            input_data: Input data for the plugin
            
        Returns:
            Plugin execution result
            
        Raises:
            SecurityError: If security violation occurs
            PluginError: If execution fails
        """
        try:
            # Create temporary execution environment
            with tempfile.TemporaryDirectory() as temp_dir:
                # Prepare execution context
                context_file = os.path.join(temp_dir, 'context.json')
                with open(context_file, 'w') as f:
                    json.dump({
                        'plugin_id': self.plugin_id,
                        'permissions': self.permissions,
                        'input': input_data,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }, f)
                
                # Execute in subprocess with security restrictions
                result = self._execute_in_sandbox(code_path, context_file, temp_dir)
                
                return result
                
        except Exception as e:
            logger.error(f"Sandbox execution failed for plugin {self.plugin_id}: {str(e)}", exc_info=True)
            raise PluginError(f"Plugin execution failed: {str(e)}")
    
    def _execute_in_sandbox(self, code_path: str, context_file: str, temp_dir: str) -> Dict[str, Any]:
        """
        Execute plugin code in a subprocess with security restrictions.
        """
        # Create restricted Python environment
        env = os.environ.copy()
        env.update({
            'PYTHONPATH': '',
            'PYTHONIOENCODING': 'utf-8',
            'PYTHONUNBUFFERED': '1'
        })
        
        # Security restrictions
        sandbox_script = f'''
import json
import sys
import os
from pathlib import Path

# Restrict imports
FORBIDDEN_MODULES = [
    'os', 'sys', 'subprocess', 'importlib', 'eval', 'exec',
    'open', 'file', 'input', 'raw_input', 'help', 'dir'
]

def secure_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name in FORBIDDEN_MODULES:
        raise SecurityError(f"Module '{{name}}' is forbidden")
    return __import__(name, globals, locals, fromlist, level)

# Override built-in functions
builtins = __builtins__
if hasattr(builtins, '__import__'):
    builtins.__import__ = secure_import

# Load context
try:
    with open('{context_file}', 'r') as f:
        context = json.load(f)
except Exception as e:
    print(json.dumps({{"error": f"Failed to load context: {{str(e)}}"}}))
    sys.exit(1)

# Execute plugin
try:
    # Load plugin code
    with open('{code_path}', 'r') as f:
        plugin_code = f.read()
    
    # Create restricted globals
    restricted_globals = {{
        '__builtins__': {{
            'print': print,
            'len': len,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            'range': range,
            'enumerate': enumerate,
            'zip': zip,
            'json': json,
            'datetime': datetime,
            'Exception': Exception,
            'ValueError': ValueError,
            'TypeError': TypeError,
            'SecurityError': SecurityError,
        }},
        'context': context,
        'input_data': context.get('input', {{}}),
        'permissions': context.get('permissions', []),
        'plugin_id': context.get('plugin_id'),
    }}
    
    # Execute plugin code
    exec(plugin_code, restricted_globals)
    
    # Get result from plugin
    if 'main' in restricted_globals:
        result = restricted_globals['main'](context['input'])
        print(json.dumps({{"result": result}}))
    else:
        print(json.dumps({{"error": "Plugin must define a main() function"}}))
        
except SecurityError as e:
    print(json.dumps({{"error": f"Security violation: {{str(e)}}"}}))
    sys.exit(1)
except Exception as e:
    print(json.dumps({{"error": f"Plugin execution error: {{str(e)}}"}}))
    sys.exit(1)
'''
        
        # Write sandbox script
        sandbox_file = os.path.join(temp_dir, 'sandbox.py')
        with open(sandbox_file, 'w') as f:
            f.write(sandbox_script)
        
        # Execute with timeout
        try:
            result = subprocess.run(
                [sys.executable, sandbox_file],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30,  # 30 second timeout
                env=env
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                raise PluginError(f"Plugin execution failed: {error_msg}")
            
            # Parse result
            output = result.stdout.strip()
            if output:
                return json.loads(output)
            else:
                return {"result": None}
                
        except subprocess.TimeoutExpired:
            raise PluginError("Plugin execution timed out")
        except json.JSONDecodeError as e:
            raise PluginError(f"Invalid plugin output: {str(e)}")


class PluginEngine:
    """
    Main plugin engine for loading, managing, and executing plugins.
    """
    
    def __init__(self, plugin_dir: str = None):
        self.plugin_dir = plugin_dir or os.path.join(os.path.dirname(__file__), '..', 'plugins')
        self.loaded_plugins = {}
        self.component_registry = {}
        self._ensure_plugin_dir()
        
    def _ensure_plugin_dir(self):
        """Ensure plugin directory exists."""
        Path(self.plugin_dir).mkdir(parents=True, exist_ok=True)
        
    def load_plugin(self, plugin_id: str, version: str = None) -> Plugin:
        """
        Load a plugin by ID and optional version.
        
        Args:
            plugin_id: Plugin identifier
            version: Plugin version (defaults to latest)
            
        Returns:
            Loaded plugin object
            
        Raises:
            ValidationError: If plugin not found or invalid
            PluginError: If loading fails
        """
        try:
            # Get plugin from database
            plugin = Plugin.objects(
                plugin_id=plugin_id,
                is_deleted=False
            ).first()
            
            if not plugin:
                raise ValidationError(f"Plugin not found: {plugin_id}")
            
            if plugin.status != 'active':
                raise ValidationError(f"Plugin is not active: {plugin_id}")
            
            # Get plugin version
            if version:
                plugin_version = PluginVersion.objects(
                    plugin_id=plugin.id,
                    version=version,
                    status='active'
                ).first()
            else:
                # Get latest version
                plugin_version = PluginVersion.objects(
                    plugin_id=plugin.id,
                    status='active'
                ).order_by('-released_at').first()
            
            if not plugin_version:
                raise ValidationError(f"Plugin version not found: {plugin_id}@{version}")
            
            # Check if already loaded
            cache_key = f"{plugin_id}@{plugin_version.version}"
            if cache_key in self.loaded_plugins:
                return self.loaded_plugins[cache_key]
            
            # Load plugin manifest
            manifest_path = os.path.join(
                plugin_version.files_path,
                'manifest.json'
            )
            
            if not os.path.exists(manifest_path):
                raise PluginError(f"Plugin manifest not found: {manifest_path}")
            
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            # Validate manifest
            self._validate_manifest(manifest)
            
            # Load component schemas
            component_schemas = []
            components_dir = os.path.join(plugin_version.files_path, 'components')
            
            if os.path.exists(components_dir):
                for component_file in os.listdir(components_dir):
                    if component_file.endswith('.json'):
                        component_path = os.path.join(components_dir, component_file)
                        with open(component_path, 'r') as f:
                            component_schema = json.load(f)
                        
                        component_schemas.append(ComponentSchema(
                            plugin_id=plugin.id,
                            plugin_version=plugin_version.version,
                            **component_schema
                        ))
            
            # Create plugin info
            plugin_info = {
                'plugin': plugin,
                'version': plugin_version,
                'manifest': manifest,
                'components': component_schemas,
                'sandbox': PluginSandbox(plugin_id, manifest.get('permissions', [])),
                'loaded_at': datetime.now(timezone.utc)
            }
            
            # Cache plugin
            self.loaded_plugins[cache_key] = plugin_info
            
            # Register components
            for component in component_schemas:
                self._register_component(component)
            
            audit_logger.info(
                f"AUDIT: Loaded plugin {plugin_id}@{plugin_version.version}"
            )
            
            return plugin
            
        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_id}: {str(e)}", exc_info=True)
            raise PluginError(f"Failed to load plugin: {str(e)}")
    
    def _validate_manifest(self, manifest: Dict[str, Any]):
        """Validate plugin manifest structure."""
        required_fields = ['plugin_id', 'name', 'version', 'permissions']
        
        for field in required_fields:
            if field not in manifest:
                raise ValidationError(f"Manifest missing required field: {field}")
        
        # Validate permissions
        allowed_permissions = {
            'db_read_own_org',
            'db_write_own_org',
            'internet_access', 
            'filesystem_read',
            'filesystem_write'
        }
        
        for permission in manifest.get('permissions', []):
            if permission not in allowed_permissions:
                raise ValidationError(f"Invalid permission: {permission}")
    
    def _register_component(self, component: ComponentSchema):
        """Register a component in the registry."""
        component_type = component.component_type
        concept = component.concept
        
        if concept not in self.component_registry:
            self.component_registry[concept] = {}
        
        if component_type not in self.component_registry[concept]:
            self.component_registry[concept][component_type] = []
        
        self.component_registry[concept][component_type].append(component)
    
    def execute_plugin(
        self,
        plugin_id: str,
        component_type: str,
        input_data: Dict[str, Any],
        organization_id: str = None,
        version: str = None
    ) -> Dict[str, Any]:
        """
        Execute a plugin component.
        
        Args:
            plugin_id: Plugin identifier
            component_type: Component type to execute
            input_data: Input data for the component
            organization_id: Organization ID (for permission checking)
            version: Plugin version (defaults to latest)
            
        Returns:
            Component execution result
            
        Raises:
            ValidationError: If plugin or component not found
            SecurityError: If permission violation
            PluginError: If execution fails
        """
        try:
            # Load plugin
            plugin_info = self.load_plugin(plugin_id, version)
            plugin = plugin_info['plugin']
            plugin_version = plugin_info['version']
            sandbox = plugin_info['sandbox']
            
            # Find component
            component = None
            for comp in plugin_info['components']:
                if comp.component_type == component_type:
                    component = comp
                    break
            
            if not component:
                raise ValidationError(f"Component not found: {component_type}")
            
            # Check permissions
            if organization_id and plugin.organization_id != organization_id:
                raise SecurityError("Plugin does not belong to this organization")
            
            # Get component handler
            handler_path = os.path.join(
                plugin_version.files_path,
                plugin.manifest.get('backend', {}).get('handler', 'handler.py')
            )
            
            if not os.path.exists(handler_path):
                raise PluginError(f"Plugin handler not found: {handler_path}")
            
            # Execute in sandbox
            result = sandbox.execute(handler_path, {
                'component_type': component_type,
                'input': input_data,
                'organization_id': organization_id,
                'component_config': component.properties
            })
            
            audit_logger.info(
                f"AUDIT: Executed plugin {plugin_id}@{plugin_version.version} "
                f"component {component_type} for org {organization_id}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to execute plugin {plugin_id}: {str(e)}", exc_info=True)
            raise PluginError(f"Plugin execution failed: {str(e)}")
    
    def get_components_by_concept(self, concept: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all components for a specific concept.
        
        Args:
            concept: Concept type (form_field, analysis_node, dashboard_widget)
            
        Returns:
            Dictionary of component types to component schemas
        """
        if concept not in self.component_registry:
            return {}
        
        result = {}
        for component_type, components in self.component_registry[concept].items():
            result[component_type] = [
                {
                    'plugin_id': comp.plugin_id,
                    'plugin_version': comp.plugin_version,
                    'component_type': comp.component_type,
                    'display_name': comp.display_name,
                    'description': comp.description,
                    'properties': comp.properties,
                    'input_ports': comp.input_ports,
                    'output_ports': comp.output_ports,
                    'offline_support': comp.offline_support
                }
                for comp in components
            ]
        
        return result
    
    def unload_plugin(self, plugin_id: str, version: str = None):
        """
        Unload a plugin from memory.
        
        Args:
            plugin_id: Plugin identifier
            version: Plugin version (if None, unload all versions)
        """
        keys_to_remove = []
        
        for cache_key, plugin_info in self.loaded_plugins.items():
            if cache_key.startswith(f"{plugin_id}@"):
                if version is None or cache_key.endswith(f"@{version}"):
                    keys_to_remove.append(cache_key)
                    
                    # Unregister components
                    for component in plugin_info['components']:
                        concept = component.concept
                        component_type = component.component_type
                        
                        if concept in self.component_registry:
                            if component_type in self.component_registry[concept]:
                                self.component_registry[concept][component_type] = [
                                    comp for comp in self.component_registry[concept][component_type]
                                    if comp.plugin_id != plugin_id
                                ]
                                
                                if not self.component_registry[concept][component_type]:
                                    del self.component_registry[concept][component_type]
        
        for key in keys_to_remove:
            del self.loaded_plugins[key]
        
        audit_logger.info(f"AUDIT: Unloaded plugin {plugin_id}@{version or 'all'}")
    
    def install_plugin(self, plugin_file_path: str, organization_id: str = None) -> Plugin:
        """
        Install a plugin from a file.
        
        Args:
            plugin_file_path: Path to plugin package file
            organization_id: Organization ID (if None, system-wide plugin)
            
        Returns:
            Installed plugin object
            
        Raises:
            ValidationError: If plugin package is invalid
            PluginError: If installation fails
        """
        try:
            # This is a simplified implementation
            # In a real implementation, this would:
            # 1. Extract and validate plugin package
            # 2. Check dependencies
            # 3. Copy files to plugin directory
            # 4. Create database records
            # 5. Load and validate plugin
            
            raise NotImplementedError("Plugin installation not yet implemented")
            
        except Exception as e:
            logger.error(f"Failed to install plugin: {str(e)}", exc_info=True)
            raise PluginError(f"Plugin installation failed: {str(e)}")
    
    def get_plugin_status(self, plugin_id: str) -> Dict[str, Any]:
        """
        Get status information for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            Plugin status information
        """
        plugin = Plugin.objects(
            plugin_id=plugin_id,
            is_deleted=False
        ).first()
        
        if not plugin:
            return {'status': 'not_found'}
        
        # Check loaded versions
        loaded_versions = []
        for cache_key, plugin_info in self.loaded_plugins.items():
            if cache_key.startswith(f"{plugin_id}@"):
                loaded_versions.append(cache_key.split('@')[1])
        
        return {
            'status': plugin.status,
            'loaded_versions': loaded_versions,
            'total_versions': PluginVersion.objects(
                plugin_id=plugin.id
            ).count()
        }