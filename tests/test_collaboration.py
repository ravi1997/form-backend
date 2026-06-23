import os
from unittest.mock import MagicMock, patch
import pytest

# Proactively patch ExportService initialization to avoid directory creation error
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Create a mock export service class
class MockExportService:
    def __init__(self):
        self.export_dir = Path("/tmp/exports")

# Force override the module before app or routes is imported
mock_exp = MagicMock()
mock_exp.export_service = MockExportService()
sys.modules['services.export_service'] = mock_exp

from app import create_app
from extensions import socketio
from flask_jwt_extended import create_access_token

@pytest.fixture(autouse=True)
def mock_export_dir(monkeypatch):
    monkeypatch.setenv("EXPORT_STORAGE_ROOT", "/tmp/exports")
    # Also patch direct settings so it doesn't fail on creation
    from config.settings import settings
    settings.EXPORT_STORAGE_ROOT = "/tmp/exports"

@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
        "JWT_SECRET_KEY": "test-jwt-secret-key-for-socketio-testing",
    })
    return app

@pytest.fixture
def socket_client(app):
    # Retrieve user token for authenticating socket connection
    with app.app_context():
        token = create_access_token(identity="test-user-123", additional_claims={"username": "Alice", "organization_id": "org-1"})
    
    # Establish flask socket client connection
    client = socketio.test_client(app, namespace='/collab', query_string=f"token={token}")
    return client

def test_connect_authenticated(socket_client):
    assert socket_client.is_connected(namespace='/collab')
    received = socket_client.get_received(namespace='/collab')
    
    auth_event = [event for event in received if event['name'] == 'authenticated']
    assert len(auth_event) == 1
    assert auth_event[0]['args'][0]['user_id'] == 'test-user-123'
    assert auth_event[0]['args'][0]['display_name'] == 'Alice'

def test_join_room_and_presence(app, socket_client):
    # Join collaboration room
    socket_client.emit('join', {
        'resource_type': 'form',
        'resource_id': 'form-abc'
    }, namespace='/collab')
    
    received = socket_client.get_received(namespace='/collab')
    presence_event = [event for event in received if event['name'] == 'presence_update']
    assert len(presence_event) == 1
    assert presence_event[0]['args'][0]['room_id'] == 'collab:form:form-abc'
    assert len(presence_event[0]['args'][0]['collaborators']) == 1
    assert presence_event[0]['args'][0]['collaborators'][0]['user_id'] == 'test-user-123'

def test_lease_acquire_and_collision(app, socket_client):
    # Join first
    socket_client.emit('join', {
        'resource_type': 'form',
        'resource_id': 'form-abc'
    }, namespace='/collab')
    socket_client.get_received(namespace='/collab') # Clear buffer
    
    # Acquire lease
    socket_client.emit('lease_acquire', {
        'room_id': 'collab:form:form-abc',
        'target': 'question-1'
    }, namespace='/collab')
    
    received = socket_client.get_received(namespace='/collab')
    lease_acquired = [event for event in received if event['name'] == 'lease_acquired']
    assert len(lease_acquired) == 1
    assert lease_acquired[0]['args'][0]['target'] == 'question-1'
    assert lease_acquired[0]['args'][0]['user_id'] == 'test-user-123'

    # Try acquiring again from another user (using another test client)
    with app.app_context():
        token2 = create_access_token(identity="test-user-456", additional_claims={"username": "Bob", "organization_id": "org-1"})
    
    client2 = socketio.test_client(app, namespace='/collab', query_string=f"token={token2}")
    client2.get_received(namespace='/collab') # Clear auth message
    client2.emit('join', {
        'resource_type': 'form',
        'resource_id': 'form-abc'
    }, namespace='/collab')
    client2.get_received(namespace='/collab') # Clear presence
    
    # Try acquiring same lock target
    client2.emit('lease_acquire', {
        'room_id': 'collab:form:form-abc',
        'target': 'question-1'
    }, namespace='/collab')
    
    received2 = client2.get_received(namespace='/collab')
    collision_event = [event for event in received2 if event['name'] == 'collision']
    assert len(collision_event) == 1
    assert collision_event[0]['args'][0]['target'] == 'question-1'
    assert collision_event[0]['args'][0]['held_by'] == 'Alice'
