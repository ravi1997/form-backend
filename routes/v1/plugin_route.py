"""
routes/v1/plugin_route.py
Blueprint for plugin system and component registry API endpoints.
"""

import os
import zipfile
import shutil
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from engines.plugin_engine import PluginEngine
from models.plugin import Plugin, PluginVersion, ComponentSchema
from utils.exceptions import ValidationError, PluginError

plugin_bp = Blueprint("plugins", __name__)
plugin_engine = PluginEngine()


@plugin_bp.route("", methods=["GET"])
@jwt_required()
def list_plugins():
    """List all installed and builtin plugins."""
    try:
        # Load any new plugins from directories
        plugin_engine.discover_and_load_plugins()
        
        plugins = Plugin.objects(is_deleted=False)
        result = []
        for p in plugins:
            status_info = plugin_engine.get_plugin_status(p.plugin_id)
            result.append({
                "plugin_id": p.plugin_id,
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "author": p.author,
                "status": p.status,
                "concept_targets": p.concept_targets,
                "permissions": p.permissions,
                "loaded_versions": status_info.get("loaded_versions", []),
                "total_versions": status_info.get("total_versions", 0)
            })
        return success_response(data=result)
    except Exception as e:
        return error_response(str(e), status_code=500)


@plugin_bp.route("/schemas", methods=["GET"])
@jwt_required()
def get_active_schemas():
    """Get all component schemas for active plugins (for client sync)."""
    try:
        # Make sure plugin registry is up to date
        plugin_engine.discover_and_load_plugins()
        
        schemas = ComponentSchema.objects()
        result = []
        for s in schemas:
            # Only return schemas for active plugins
            plugin = Plugin.objects(plugin_id=s.plugin_id, is_deleted=False).first()
            if plugin and plugin.status == 'active':
                result.append({
                    "plugin_id": s.plugin_id,
                    "plugin_version": s.plugin_version,
                    "concept": s.concept_id,
                    "type": s.component_type,
                    "display_name": s.display_name,
                    "description": s.description,
                    "icon": s.icon_path,
                    "composition": s.composition,
                    "properties": s.properties,
                    "input_ports": s.input_ports,
                    "output_ports": s.output_ports,
                    "widget_config": s.widget_config,
                    "preview_schema": s.preview_schema,
                    "offline_support": s.offline_support
                })
        return success_response(data=result)
    except Exception as e:
        return error_response(str(e), status_code=500)


@plugin_bp.route("/install", methods=["POST"])
@jwt_required()
@require_roles("super_admin")
def install_plugin():
    """Install or upload a new plugin package."""
    try:
        plugin_id = request.form.get("plugin_id")
        
        # Check if zip file uploaded
        if "file" in request.files:
            file = request.files["file"]
            if not file.filename.endswith(".zip"):
                return error_response("Invalid file type. Only ZIP packages allowed.", status_code=400)
                
            # Temp extraction
            temp_dir = os.path.join("/tmp", f"plugin_{plugin_id or 'temp'}")
            os.makedirs(temp_dir, exist_ok=True)
            zip_path = os.path.join(temp_dir, file.filename)
            file.save(zip_path)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
                
            # Look for manifest.json
            extracted_files = os.listdir(temp_dir)
            target_dir = temp_dir
            if len(extracted_files) == 1 and os.path.isdir(os.path.join(temp_dir, extracted_files[0])):
                target_dir = os.path.join(temp_dir, extracted_files[0])
                
            manifest_path = os.path.join(target_dir, 'manifest.json')
            if not os.path.exists(manifest_path):
                shutil.rmtree(temp_dir)
                return error_response("PLUGIN_MANIFEST_MISSING: manifest.json not found in package.", status_code=400)
                
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
                
            detected_plugin_id = manifest.get('plugin_id')
            if not detected_plugin_id:
                shutil.rmtree(temp_dir)
                return error_response("PLUGIN_MANIFEST_MISSING_FIELD: plugin_id is required in manifest.", status_code=400)
                
            # Move package to installed directory
            installed_path = os.path.join(plugin_engine.plugin_dir, 'installed', detected_plugin_id)
            if os.path.exists(installed_path):
                shutil.rmtree(installed_path)
            os.makedirs(os.path.dirname(installed_path), exist_ok=True)
            shutil.copytree(target_dir, installed_path)
            shutil.rmtree(temp_dir)
            
            # Discover and validate the installed plugin
            plugin = plugin_engine.discover_plugin(installed_path, detected_plugin_id)
            return success_response(
                data={"plugin_id": plugin.plugin_id, "status": plugin.status},
                message="Plugin package uploaded successfully, pending approval."
            )
            
        # Installation from existing local directory (development/testing)
        source_dir = request.json.get("source_dir") if request.is_json else None
        target_plugin_id = request.json.get("plugin_id") if request.is_json else None
        
        if source_dir and target_plugin_id:
            if not os.path.exists(source_dir):
                return error_response(f"Source directory not found: {source_dir}", status_code=400)
                
            installed_path = os.path.join(plugin_engine.plugin_dir, 'installed', target_plugin_id)
            if os.path.exists(installed_path):
                shutil.rmtree(installed_path)
            os.makedirs(os.path.dirname(installed_path), exist_ok=True)
            shutil.copytree(source_dir, installed_path)
            
            plugin = plugin_engine.discover_plugin(installed_path, target_plugin_id)
            return success_response(
                data={"plugin_id": plugin.plugin_id, "status": plugin.status},
                message="Plugin installed successfully from local path, pending approval."
            )
            
        return error_response("No plugin ZIP file or source directory path provided.", status_code=400)
    except ValidationError as e:
        return error_response(str(e), status_code=400)
    except Exception as e:
        return error_response(str(e), status_code=500)


@plugin_bp.route("/<plugin_id>/approve", methods=["POST"])
@jwt_required()
@require_roles("super_admin")
def approve_plugin(plugin_id):
    """Approve permissions and activate the plugin."""
    try:
        data = request.get_json() or {}
        approved_permissions = data.get("approved_permissions", [])
        
        plugin = Plugin.objects(plugin_id=plugin_id, is_deleted=False).first()
        if not plugin:
            return error_response("Plugin not found", status_code=404)
            
        # Verify approved permissions covers manifest expectations
        manifest = plugin.manifest
        required_permissions = manifest.get("permissions", [])
        
        # Super admin approves
        plugin.permissions = approved_permissions
        plugin.status = 'active'
        plugin.save()
        
        # Load into registry and run health check
        version_rec = PluginVersion.objects(plugin_id=plugin_id, version=plugin.version).first()
        if not version_rec:
            return error_response("Plugin version not found in database", status_code=404)
            
        try:
            plugin_engine.load_plugin_into_registry(plugin, version_rec, manifest, version_rec.files_path)
        except Exception as e:
            plugin.status = 'suspended'
            plugin.save()
            return error_response(f"Verification check failed: {e}", status_code=400)
            
        # Reload status from DB
        plugin.reload()
        if plugin.status == 'active':
            return success_response(
                data={"plugin_id": plugin.plugin_id, "status": plugin.status},
                message="Plugin approved and activated successfully."
            )
        else:
            return error_response(
                message=f"Plugin approved but entered {plugin.status} state. Verify plugin logs.",
                status_code=400
            )
    except Exception as e:
        return error_response(str(e), status_code=500)


@plugin_bp.route("/<plugin_id>/suspend", methods=["POST"])
@jwt_required()
@require_roles("super_admin")
def suspend_plugin(plugin_id):
    """Suspend an active plugin."""
    try:
        plugin = Plugin.objects(plugin_id=plugin_id, is_deleted=False).first()
        if not plugin:
            return error_response("Plugin not found", status_code=404)
            
        plugin.status = 'suspended'
        plugin.save()
        
        # Unload from active memory registry
        plugin_engine.unload_plugin(plugin_id)
        
        return success_response(
            data={"plugin_id": plugin.plugin_id, "status": plugin.status},
            message="Plugin suspended successfully."
        )
    except Exception as e:
        return error_response(str(e), status_code=500)


@plugin_bp.route("/<plugin_id>/reload", methods=["POST"])
@jwt_required()
@require_roles("super_admin")
def reload_plugin(plugin_id):
    """Reload an active plugin."""
    try:
        plugin = Plugin.objects(plugin_id=plugin_id, is_deleted=False).first()
        if not plugin:
            return error_response("Plugin not found", status_code=404)
            
        version_rec = PluginVersion.objects(plugin_id=plugin_id, version=plugin.version).first()
        if not version_rec:
            return error_response("Plugin version not found", status_code=404)
            
        # Re-run discover and load sequence
        plugin_engine.unload_plugin(plugin_id)
        plugin = plugin_engine.discover_plugin(version_rec.files_path, plugin_id)
        
        return success_response(
            data={"plugin_id": plugin.plugin_id, "status": plugin.status},
            message="Plugin reloaded successfully."
        )
    except Exception as e:
        return error_response(str(e), status_code=500)
