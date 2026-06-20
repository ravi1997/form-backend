import pytest
import os
import json
import shutil
import tempfile
import mongoengine
import mongomock
from flask import Flask
from models.plugin import Plugin, PluginVersion, ComponentSchema, ConceptRegistry
from engines.plugin_engine import PluginEngine, PluginSandbox
from routes.v1.plugin_route import plugin_bp
from utils.exceptions import ValidationError, PluginError


@pytest.fixture(scope="session", autouse=True)
def setup_mongo_connection():
    # Use mongomock to avoid running actual mongodb instances
    mongoengine.connect('test_db', mongo_client_class=mongomock.MongoClient)


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(plugin_bp, url_prefix='/api/internal/v1/plugins')
    app.config['JWT_SECRET_KEY'] = 'test-secret'
    app.config['JWT_TOKEN_LOCATION'] = ['headers']
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {
        'Authorization': 'Bearer test-token',
        'Content-Type': 'application/json'
    }


@pytest.fixture
def mock_plugin_package():
    # Set up a temporary directory with a valid plugin anatomy
    temp_dir = tempfile.mkdtemp()
    
    manifest = {
        "plugin_id": "test-plugin",
        "name": "Test Plugin",
        "version": "1.0.0",
        "min_platform_version": "1.0.0",
        "author": {
            "name": "John Doe",
            "email": "john@doe.com"
        },
        "description": "A test plugin component.",
        "concept_targets": ["form_field"],
        "permissions": ["db_read_own_org"],
        "backend": {
            "handler": "handler.py"
        },
        "components": [
            {
                "type": "test_text_field",
                "schema": "component_schema.json",
                "icon": "icon.svg",
                "concept": "form_field"
            }
        ]
    }
    
    with open(os.path.join(temp_dir, 'manifest.json'), 'w') as f:
        json.dump(manifest, f)
        
    schema = {
        "display_name": "Test Input Field",
        "description": "Custom test field",
        "concept": "form_field",
        "properties": [
            {"key": "label", "label": "Label", "type": "string", "default": "Custom Text"}
        ]
    }
    
    with open(os.path.join(temp_dir, 'component_schema.json'), 'w') as f:
        json.dump(schema, f)
        
    with open(os.path.join(temp_dir, 'icon.svg'), 'w') as f:
        f.write('<svg></svg>')
        
    handler_code = """
import sys
import json

def main():
    input_str = sys.stdin.read().strip()
    if not input_str:
        return
    payload = json.loads(input_str)
    
    if payload.get('action') == 'ping':
        print(json.dumps({"status": "ok"}))
        return
        
    inp = payload.get('input', {})
    print(json.dumps({"result": f"hello {inp.get('name', 'world')}"}))

if __name__ == '__main__':
    main()
"""
    with open(os.path.join(temp_dir, 'handler.py'), 'w') as f:
        f.write(handler_code)
        
    yield temp_dir
    
    shutil.rmtree(temp_dir)


class TestPluginSystem:

    def test_manifest_validation(self, mock_plugin_package):
        engine = PluginEngine(plugin_dir=tempfile.mkdtemp())
        engine.seed_concepts()
        
        # Manifest parsing / validation
        manifest_path = os.path.join(mock_plugin_package, 'manifest.json')
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
            
        # Should succeed on valid manifest
        engine._validate_manifest(manifest, mock_plugin_package)
        
        # Fails with missing field
        invalid_manifest = manifest.copy()
        del invalid_manifest['name']
        with pytest.raises(ValidationError):
            engine._validate_manifest(invalid_manifest, mock_plugin_package)

    def test_sandbox_ping_and_execution(self, mock_plugin_package):
        sandbox = PluginSandbox("test-plugin", ["db_read_own_org"])
        handler_path = os.path.join(mock_plugin_package, 'handler.py')
        
        # Test ping action
        ping_res = sandbox.execute(handler_path, {"action": "ping"}, mock_plugin_package)
        assert ping_res.get('status') == 'ok'
        
        # Test business logic execution
        exec_res = sandbox.execute(handler_path, {"input": {"name": "Alice"}}, mock_plugin_package)
        assert exec_res.get('result') == 'hello Alice'

    def test_endpoint_schemas_sync(self, client, auth_headers, mock_plugin_package):
        # Seed concept database
        ConceptRegistry.objects(concept_id="form_field").update_one(
            set__name="Form Field",
            set__builder_type="form_builder",
            set__is_system=True,
            upsert=True
        )
        
        # Test schemas listing when no active schemas exist
        from unittest.mock import patch
        with patch('flask_jwt_extended.view_decorators.verify_jwt_in_request', return_value=None):
            
            # Seed plugin engine directory
            engine = PluginEngine()
            
            # Install plugin manually
            installed_path = os.path.join(engine.plugin_dir, 'installed', 'test-plugin')
            if os.path.exists(installed_path):
                shutil.rmtree(installed_path)
            shutil.copytree(mock_plugin_package, installed_path)
            
            # Discover
            plugin = engine.discover_plugin(installed_path, 'test-plugin')
            assert plugin.status == 'pending'
            
            # Approve it to register component schemas
            plugin.status = 'active'
            plugin.save()
            version_rec = PluginVersion.objects(plugin_id='test-plugin', version='1.0.0').first()
            engine.load_plugin_into_registry(plugin, version_rec, plugin.manifest, installed_path)
            
            response = client.get('/api/internal/v1/plugins/schemas', headers=auth_headers)
            assert response.status_code == 200
            res_json = json.loads(response.data)
            assert res_json.get('success') is True
            schemas = res_json.get('data', [])
            assert len(schemas) > 0
            assert schemas[0]['type'] == 'test_text_field'
            
            # Clean up
            shutil.rmtree(installed_path)
            ComponentSchema.objects(plugin_id='test-plugin').delete()
            Plugin.objects(plugin_id='test-plugin').delete()
            PluginVersion.objects(plugin_id='test-plugin').delete()
