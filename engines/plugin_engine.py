"""
engines/plugin_engine.py
Plugin engine for loading, executing, and managing plugins with sandbox security.
Provides a secure environment for plugin execution with proper permission isolation.
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path

from models.plugin import Plugin, PluginVersion, ComponentSchema, ConceptRegistry
from utils.exceptions import PluginError, ValidationError
from logger.unified_logger import audit_logger
from config.settings import settings

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
                raise ValidationError(f"PLUGIN_UNKNOWN_PERMISSION: Permission not allowed: {perm}")
    
    def execute(self, handler_path: str, context_payload: Dict[str, Any], plugin_path: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Execute plugin code in a secure sandbox subprocess environment using stdin/stdout.
        """
        # Whitelisted sandbox environment
        allowed_env = {
            'PATH': os.environ.get('PATH', ''),
            'PLUGIN_ID': self.plugin_id,
            'PLUGIN_VERSION': context_payload.get('plugin_version', '1.0.0'),
            'ORG_ID': context_payload.get('org_id', ''),
            'PLATFORM_VERSION': settings.PLATFORM_VERSION,
            'PYTHONPATH': plugin_path,
            'PYTHONHASHSEED': '0',
            'PYTHONIOENCODING': 'utf-8',
            'PYTHONUNBUFFERED': '1'
        }
        
        # Use venv Python if it exists, otherwise fall back to system python
        venv_python = os.path.join('/var/plugins_venvs', self.plugin_id, 'bin', 'python')
        if not os.path.exists(venv_python):
            venv_python = sys.executable

        try:
            proc = subprocess.Popen(
                [venv_python, handler_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=allowed_env,
                cwd=plugin_path
            )
            
            stdout_data, stderr_data = proc.communicate(
                input=(json.dumps(context_payload) + '\n').encode('utf-8'),
                timeout=timeout
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            raise PluginError("Plugin execution timed out")
        except Exception as e:
            raise PluginError(f"Failed to spawn plugin process: {e}")
            
        if proc.returncode != 0:
            error_msg = stderr_data.decode('utf-8') or stdout_data.decode('utf-8')
            raise PluginError(f"Plugin execution failed with code {proc.returncode}: {error_msg}")
            
        try:
            return json.loads(stdout_data.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise PluginError(f"Invalid JSON response from plugin: {stdout_data.decode('utf-8')}")


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
        Path(os.path.join(self.plugin_dir, 'builtin')).mkdir(parents=True, exist_ok=True)
        Path(os.path.join(self.plugin_dir, 'installed')).mkdir(parents=True, exist_ok=True)

    def seed_concepts(self):
        """Seed built-in plugin concepts if they don't exist."""
        default_concepts = [
            {"concept_id": "form_field", "name": "Form Field", "builder_type": "form_builder", "is_system": True},
            {"concept_id": "analysis_node", "name": "Analysis Node", "builder_type": "analysis_coder", "is_system": True},
            {"concept_id": "dashboard_widget", "name": "Dashboard Widget", "builder_type": "dashboard_builder", "is_system": True}
        ]
        for dc in default_concepts:
            if not ConceptRegistry.objects(concept_id=dc["concept_id"]).first():
                ConceptRegistry(**dc).save()
        
    def discover_and_load_plugins(self):
        """Scan both builtin and installed directories and register plugins."""
        self.seed_concepts()
        
        # Discovery
        for folder in ['builtin', 'installed']:
            dir_path = os.path.join(self.plugin_dir, folder)
            if not os.path.exists(dir_path):
                continue
            for plugin_id in os.listdir(dir_path):
                plugin_path = os.path.join(dir_path, plugin_id)
                if os.path.isdir(plugin_path):
                    try:
                        self.discover_plugin(plugin_path, plugin_id, is_builtin=(folder == 'builtin'))
                    except Exception as e:
                        logger.error(f"Error discovering plugin {plugin_id}: {e}")

    def discover_plugin(self, plugin_path: str, plugin_id: str, is_builtin: bool = False) -> Plugin:
        """Discover, validate manifest, and save/register plugin metadata."""
        manifest_path = os.path.join(plugin_path, 'manifest.json')
        if not os.path.exists(manifest_path):
            raise ValidationError(f"PLUGIN_MANIFEST_MISSING: manifest.json not found in {plugin_path}")
            
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
        except Exception as e:
            raise ValidationError(f"PLUGIN_MANIFEST_INVALID_JSON: Failed to parse manifest JSON: {e}")
            
        # Parse & validate manifest fields
        self._validate_manifest(manifest, plugin_path)
        
        # Check database records
        plugin = Plugin.objects(plugin_id=plugin_id, is_deleted=False).first()
        if not plugin:
            plugin = Plugin(
                plugin_id=plugin_id,
                name=manifest['name'],
                description=manifest.get('description'),
                author=manifest.get('author'),
                version=manifest['version'],
                manifest=manifest,
                status='pending', # New plugins start as pending approval
                concept_targets=manifest.get('concept_targets', []),
                permissions=manifest.get('permissions', []),
                created_at=datetime.now(timezone.utc)
            )
            plugin.save()
        else:
            # Upgrade scenario
            if plugin.version != manifest['version']:
                plugin.version = manifest['version']
                plugin.manifest = manifest
                plugin.concept_targets = manifest.get('concept_targets', [])
                plugin.permissions = manifest.get('permissions', [])
                plugin.updated_at = datetime.now(timezone.utc)
                plugin.save()

        # Update PluginVersion
        version_rec = PluginVersion.objects(plugin_id=plugin_id, version=manifest['version']).first()
        if not version_rec:
            version_rec = PluginVersion(
                plugin_id=plugin_id,
                version=manifest['version'],
                manifest=manifest,
                files_path=plugin_path,
                status='active',
                released_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc)
            )
            version_rec.save()

        # If plugin is active, register its components and run health check
        if plugin.status == 'active':
            self.load_plugin_into_registry(plugin, version_rec, manifest, plugin_path)

        return plugin

    def load_plugin_into_registry(self, plugin: Plugin, plugin_version: PluginVersion, manifest: Dict[str, Any], plugin_path: str):
        """Loads components from active plugin into DB and memory registry."""
        cache_key = f"{plugin.plugin_id}@{plugin_version.version}"
        
        # Register component schemas in MongoDB
        component_schemas = []
        for comp_desc in manifest.get('components', []):
            schema_rel_path = comp_desc['schema']
            schema_abs_path = os.path.join(plugin_path, schema_rel_path)
            
            if not os.path.exists(schema_abs_path):
                raise ValidationError(f"PLUGIN_SCHEMA_NOT_FOUND: Schema file {schema_rel_path} does not exist.")
                
            with open(schema_abs_path, 'r') as f:
                schema_json = json.load(f)
                
            # Upsert into component_schemas collection
            comp_type = comp_desc['type']
            db_schema = ComponentSchema.objects(
                plugin_id=plugin.plugin_id,
                plugin_version=plugin_version.version,
                component_type=comp_type
            ).first()
            
            if not db_schema:
                db_schema = ComponentSchema(
                    plugin_id=plugin.plugin_id,
                    plugin_version=plugin_version.version,
                    concept_id=comp_desc['concept'],
                    component_type=comp_type,
                    display_name=schema_json.get('display_name', comp_type),
                    description=schema_json.get('description', ''),
                    icon_path=comp_desc.get('icon', ''),
                    composition=schema_json.get('composition', []),
                    properties=schema_json.get('properties', []),
                    input_ports=schema_json.get('input_ports', []),
                    output_ports=schema_json.get('output_ports', []),
                    widget_config=schema_json.get('widget_config', {}),
                    preview_schema=schema_json.get('preview_schema', {}),
                    offline_support=schema_json.get('offline_support', False),
                    created_at=datetime.now(timezone.utc)
                )
            else:
                db_schema.display_name = schema_json.get('display_name', comp_type)
                db_schema.description = schema_json.get('description', '')
                db_schema.composition = schema_json.get('composition', [])
                db_schema.properties = schema_json.get('properties', [])
                db_schema.input_ports = schema_json.get('input_ports', [])
                db_schema.output_ports = schema_json.get('output_ports', [])
                db_schema.widget_config = schema_json.get('widget_config', {})
                db_schema.preview_schema = schema_json.get('preview_schema', {})
                db_schema.offline_support = schema_json.get('offline_support', False)
                db_schema.updated_at = datetime.now(timezone.utc)
                
            db_schema.save()
            component_schemas.append(db_schema)

        # Health ping check for backend handler
        if 'backend' in manifest and 'handler' in manifest['backend']:
            handler_path = os.path.join(plugin_path, manifest['backend']['handler'])
            sandbox = PluginSandbox(plugin.plugin_id, manifest.get('permissions', []))
            
            # Execute ping check
            try:
                ping_res = sandbox.execute(
                    handler_path=handler_path,
                    context_payload={"action": "ping"},
                    plugin_path=plugin_path,
                    timeout=5
                )
                if ping_res.get('status') != 'ok':
                    plugin.status = 'suspended'
                    plugin.save()
                    logger.warning(f"Plugin {plugin.plugin_id} suspended due to invalid ping status: {ping_res}")
                    return
            except Exception as e:
                plugin.status = 'suspended'
                plugin.save()
                logger.error(f"Plugin {plugin.plugin_id} suspended due to ping failure: {e}")
                return

        # Cache in memory
        self.loaded_plugins[cache_key] = {
            'plugin': plugin,
            'version': plugin_version,
            'manifest': manifest,
            'components': component_schemas,
            'sandbox': PluginSandbox(plugin.plugin_id, manifest.get('permissions', [])),
            'loaded_at': datetime.now(timezone.utc)
        }
        
        # Register in component registry
        for schema in component_schemas:
            self._register_component(schema)

    def load_plugin(self, plugin_id: str, version: str = None) -> Plugin:
        """Load a plugin by ID and optional version."""
        plugin = Plugin.objects(plugin_id=plugin_id, is_deleted=False).first()
        if not plugin:
            raise ValidationError(f"Plugin not found: {plugin_id}")
            
        if plugin.status != 'active':
            raise ValidationError(f"Plugin is not active: {plugin_id}")
            
        if version:
            plugin_version = PluginVersion.objects(plugin_id=plugin_id, version=version, status='active').first()
        else:
            plugin_version = PluginVersion.objects(plugin_id=plugin_id, status='active').order_by('-released_at').first()
            
        if not plugin_version:
            raise ValidationError(f"Plugin version not found for {plugin_id}")
            
        cache_key = f"{plugin_id}@{plugin_version.version}"
        if cache_key in self.loaded_plugins:
            return self.loaded_plugins[cache_key]['plugin']
            
        self.load_plugin_into_registry(plugin, plugin_version, plugin.manifest, plugin_version.files_path)
        return plugin
    
    def _validate_manifest(self, manifest: Dict[str, Any], plugin_path: str):
        """Validate plugin manifest structure and fields."""
        required_fields = ['plugin_id', 'name', 'version', 'author', 'description', 'concept_targets', 'permissions', 'components']
        for field in required_fields:
            if field not in manifest:
                raise ValidationError(f"PLUGIN_MANIFEST_MISSING_FIELD: Manifest missing required field: {field}")
                
        # Validate author
        author = manifest['author']
        if not isinstance(author, dict) or 'name' not in author or 'email' not in author:
            raise ValidationError("PLUGIN_MANIFEST_MISSING_FIELD: Author object must contain name and email.")
            
        # Validate version
        version = manifest['version']
        import re
        if not re.match(r'^\d+\.\d+\.\d+$', version):
            raise ValidationError(f"PLUGIN_MANIFEST_INVALID_FIELD: Version must be semantic MAJOR.MINOR.PATCH format.")
            
        # Validate platform version
        min_p = manifest.get('min_platform_version', '0.0.0')
        max_p = manifest.get('max_platform_version', '999.999.999')
        # Check compatibility (simple check)
        from distutils.version import LooseVersion
        plat_ver = settings.PLATFORM_VERSION
        if LooseVersion(plat_ver) < LooseVersion(min_p):
            raise ValidationError("PLUGIN_PLATFORM_VERSION_TOO_LOW")
        if LooseVersion(plat_ver) > LooseVersion(max_p):
            raise ValidationError("PLUGIN_PLATFORM_VERSION_TOO_HIGH")

        # Validate concept targets against registry
        for concept in manifest.get('concept_targets', []):
            if not ConceptRegistry.objects(concept_id=concept).first():
                raise ValidationError(f"PLUGIN_UNKNOWN_CONCEPT: Unknown concept target: {concept}")

        # Validate permissions
        allowed_permissions = {
            'db_read_own_org',
            'db_write_own_org', 
            'internet_access',
            'filesystem_read',
            'filesystem_write'
        }
        for perm in manifest.get('permissions', []):
            if perm not in allowed_permissions:
                raise ValidationError(f"PLUGIN_UNKNOWN_PERMISSION: Unknown permission: {perm}")

        # Validate files exist
        if 'backend' in manifest and 'handler' in manifest['backend']:
            handler_rel = manifest['backend']['handler']
            if not os.path.exists(os.path.join(plugin_path, handler_rel)):
                raise ValidationError("PLUGIN_HANDLER_NOT_FOUND")

        for comp in manifest.get('components', []):
            for req in ['type', 'schema', 'icon', 'concept']:
                if req not in comp:
                    raise ValidationError(f"PLUGIN_MANIFEST_MISSING_FIELD: Component missing field: {req}")
            if not os.path.exists(os.path.join(plugin_path, comp['schema'])):
                raise ValidationError("PLUGIN_SCHEMA_NOT_FOUND")
            if not os.path.exists(os.path.join(plugin_path, comp['icon'])):
                raise ValidationError("PLUGIN_ICON_NOT_FOUND")
            
    def _register_component(self, component: ComponentSchema):
        """Register a component in the registry."""
        component_type = component.component_type
        concept = component.concept_id
        
        if concept not in self.component_registry:
            self.component_registry[concept] = {}
        
        if component_type not in self.component_registry[concept]:
            self.component_registry[concept][component_type] = []
        
        # Replace if version matches, otherwise append
        self.component_registry[concept][component_type] = [
            c for c in self.component_registry[concept][component_type]
            if not (c.plugin_id == component.plugin_id and c.plugin_version == component.plugin_version)
        ]
        self.component_registry[concept][component_type].append(component)
    
    def execute_plugin(
        self,
        plugin_id: str,
        component_type: str,
        input_data: Dict[str, Any],
        organization_id: str = None,
        version: str = None
    ) -> Dict[str, Any]:
        """Execute a plugin component."""
        # Ensure plugin loaded
        self.load_plugin(plugin_id, version)
        
        # Get plugin info
        cache_key = None
        for key in self.loaded_plugins:
            if key.startswith(f"{plugin_id}@"):
                if version is None or key.endswith(f"@{version}"):
                    cache_key = key
                    break
        if not cache_key:
            raise ValidationError(f"Plugin loaded cache key not found: {plugin_id}")
            
        plugin_info = self.loaded_plugins[cache_key]
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
            
        # Get component handler
        handler_path = os.path.join(
            plugin_version.files_path,
            plugin.manifest.get('backend', {}).get('handler', 'backend/handler.py')
        )
        
        if not os.path.exists(handler_path):
            raise PluginError(f"Plugin handler not found: {handler_path}")
            
        # Execute in sandbox
        result = sandbox.execute(
            handler_path=handler_path,
            context_payload={
                'plugin_version': plugin_version.version,
                'component_type': component_type,
                'input': input_data,
                'organization_id': organization_id,
                'component_config': component.properties
            },
            plugin_path=plugin_version.files_path
        )
        
        audit_logger.info(
            f"AUDIT: Executed plugin {plugin_id}@{plugin_version.version} "
            f"component {component_type} for org {organization_id}"
        )
        
        return result
    
    def get_components_by_concept(self, concept: str) -> Dict[str, List[Dict[str, Any]]]:
        """Get all components for a specific concept."""
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
        """Unload a plugin from memory and registry."""
        keys_to_remove = []
        
        for cache_key, plugin_info in self.loaded_plugins.items():
            if cache_key.startswith(f"{plugin_id}@"):
                if version is None or cache_key.endswith(f"@{version}"):
                    keys_to_remove.append(cache_key)
                    
                    # Unregister components
                    for component in plugin_info['components']:
                        concept = component.concept_id
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
    
    def get_plugin_status(self, plugin_id: str) -> Dict[str, Any]:
        """Get status information for a plugin."""
        plugin = Plugin.objects(plugin_id=plugin_id, is_deleted=False).first()
        if not plugin:
            return {'status': 'not_found'}
            
        loaded_versions = []
        for cache_key in self.loaded_plugins:
            if cache_key.startswith(f"{plugin_id}@"):
                loaded_versions.append(cache_key.split('@')[1])
                
        return {
            'status': plugin.status,
            'loaded_versions': loaded_versions,
            'total_versions': PluginVersion.objects(plugin_id=plugin.id).count()
        }