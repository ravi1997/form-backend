import pytest
import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from flask import Flask
from routes.v1.sync_route import sync_bp
from models import Form, Project, Dashboard
from models.utility import Tombstone
from services.tombstone_service import TombstoneService


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(sync_bp, url_prefix='/api/internal/v1/sync')
    
    # Add required JWT configuration
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
def mock_user():
    user = Mock()
    user.id = 'user_123'
    user.organization_id = 'org_456'
    return user


@pytest.fixture
def sample_form():
    form = Mock()
    form.id = 'form_123'
    form.organization_id = 'org_456'
    form.project_id = 'project_789'
    form.title = 'Test Form'
    form.description = 'A test form'
    form.form_fields = {'fields': []}
    form.updated_at = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
    return form


@pytest.fixture
def sample_project():
    project = Mock()
    project.id = 'project_123'
    project.organization_id = 'org_456'
    project.name = 'Test Project'
    project.description = 'A test project'
    project.updated_at = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
    return project


@pytest.fixture
def sample_dashboard():
    dashboard = Mock()
    dashboard.id = 'dashboard_123'
    dashboard.organization_id = 'org_456'
    dashboard.project_id = 'project_789'
    dashboard.name = 'Test Dashboard'
    dashboard.description = 'A test dashboard'
    dashboard.canvas = {'widgets': []}
    dashboard.settings = {'theme': 'default'}
    dashboard.linked_analysis_ids = ['analysis_123']
    dashboard.updated_at = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
    return dashboard


@pytest.fixture
def sample_tombstone():
    return {
        'entity_type': 'forms',
        'entity_id': 'form_456',
        'deleted_at': datetime(2026, 6, 19, 11, 0, 0, tzinfo=timezone.utc)
    }


class TestDeltaSyncEndpoint:
    
    def test_get_delta_sync_no_timestamp(self, client, auth_headers, mock_user, sample_form, sample_tombstone):
        """Test delta sync without last_synced_at parameter"""
        with patch('routes.v1.sync_route.get_current_user', return_value=mock_user), \
             patch.object(Form, 'objects') as mock_forms_query, \
             patch.object(TombstoneService, 'list_since') as mock_tombstone_service:
            
            # Setup mocks
            mock_forms_query.return_value.filter.return_value.only.return_value.limit.return_value = [sample_form]
            mock_tombstone_service.return_value = [sample_tombstone]
            
            response = client.get('/api/internal/v1/sync', headers=auth_headers)
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            assert 'updated' in data
            assert 'tombstones' in data
            assert 'server_timestamp' in data
            assert len(data['updated']) == 1
            assert data['updated'][0]['id'] == 'form_123'
            assert len(data['tombstones']) == 1
            assert data['tombstones'][0]['entity_type'] == 'forms'
    
    def test_get_delta_sync_with_timestamp(self, client, auth_headers, mock_user, sample_form):
        """Test delta sync with last_synced_at parameter"""
        with patch('routes.v1.sync_route.get_current_user', return_value=mock_user), \
             patch.object(Form, 'objects') as mock_forms_query, \
             patch.object(TombstoneService, 'list_since') as mock_tombstone_service:
            
            # Setup mocks
            mock_forms_query.return_value.filter.return_value.only.return_value.limit.return_value = [sample_form]
            mock_tombstone_service.return_value = []
            
            last_synced = '2026-06-19T10:00:00Z'
            response = client.get(f'/api/internal/v1/sync?last_synced_at={last_synced}', headers=auth_headers)
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            # Verify the timestamp filter was applied
            mock_forms_query.return_value.filter.assert_called()
            mock_tombstone_service.assert_called_once()
    
    def test_get_delta_sync_with_entity_types(self, client, auth_headers, mock_user):
        """Test delta sync with entity_types parameter"""
        with patch('routes.v1.sync_route.get_current_user', return_value=mock_user), \
             patch.object(Form, 'objects') as mock_forms_query, \
             patch.object(Project, 'objects') as mock_projects_query, \
             patch.object(Dashboard, 'objects') as mock_dashboards_query, \
             patch.object(TombstoneService, 'list_since') as mock_tombstone_service:
            
            # Setup mocks
            mock_forms_query.return_value.filter.return_value.only.return_value.limit.return_value = []
            mock_projects_query.return_value.filter.return_value.only.return_value.limit.return_value = []
            mock_dashboards_query.return_value.filter.return_value.only.return_value.limit.return_value = []
            mock_tombstone_service.return_value = []
            
            response = client.get('/api/internal/v1/sync?entity_types=forms,projects', headers=auth_headers)
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            # Verify all specified entity types were queried
            mock_forms_query.assert_called_once()
            mock_projects_query.assert_called_once()
            mock_dashboards_query.assert_not_called()  # Not in entity_types
    
    def test_get_delta_sync_invalid_timestamp(self, client, auth_headers, mock_user):
        """Test delta sync with invalid timestamp format"""
        response = client.get('/api/internal/v1/sync?last_synced_at=invalid-timestamp', headers=auth_headers)
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Invalid last_synced_at format' in data['error']['message']
    
    def test_get_delta_sync_all_entity_types(self, client, auth_headers, mock_user, sample_form, sample_project, sample_dashboard):
        """Test delta sync returning all entity types"""
        with patch('routes.v1.sync_route.get_current_user', return_value=mock_user), \
             patch.object(Form, 'objects') as mock_forms_query, \
             patch.object(Project, 'objects') as mock_projects_query, \
             patch.object(Dashboard, 'objects') as mock_dashboards_query, \
             patch.object(TombstoneService, 'list_since') as mock_tombstone_service:
            
            # Setup mocks
            mock_forms_query.return_value.filter.return_value.only.return_value.limit.return_value = [sample_form]
            mock_projects_query.return_value.filter.return_value.only.return_value.limit.return_value = [sample_project]
            mock_dashboards_query.return_value.filter.return_value.only.return_value.limit.return_value = [sample_dashboard]
            mock_tombstone_service.return_value = []
            
            response = client.get('/api/internal/v1/sync', headers=auth_headers)
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            # Verify all entity types are returned
            entity_types = {item['entityType'] for item in data['updated']}
            assert 'forms' in entity_types
            assert 'projects' in entity_types
            assert 'dashboards' in entity_types
    
    def test_get_delta_sync_empty_results(self, client, auth_headers, mock_user):
        """Test delta sync with no updates or tombstones"""
        with patch('routes.v1.sync_route.get_current_user', return_value=mock_user), \
             patch.object(Form, 'objects') as mock_forms_query, \
             patch.object(Project, 'objects') as mock_projects_query, \
             patch.object(Dashboard, 'objects') as mock_dashboards_query, \
             patch.object(TombstoneService, 'list_since') as mock_tombstone_service:
            
            # Setup mocks to return empty results
            mock_forms_query.return_value.filter.return_value.only.return_value.limit.return_value = []
            mock_projects_query.return_value.filter.return_value.only.return_value.limit.return_value = []
            mock_dashboards_query.return_value.filter.return_value.only.return_value.limit.return_value = []
            mock_tombstone_service.return_value = []
            
            response = client.get('/api/internal/v1/sync', headers=auth_headers)
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            assert data['updated'] == []
            assert data['tombstones'] == []
            assert 'server_timestamp' in data
    
    def test_get_delta_sync_server_error(self, client, auth_headers, mock_user):
        """Test delta sync with server error"""
        with patch('routes.v1.sync_route.get_current_user', return_value=mock_user), \
             patch.object(Form, 'objects') as mock_forms_query:
            
            # Setup mock to raise exception
            mock_forms_query.side_effect = Exception("Database error")
            
            response = client.get('/api/internal/v1/sync', headers=auth_headers)
            
            assert response.status_code == 500
            data = json.loads(response.data)
            assert 'error' in data
    
    def test_get_delta_sync_tombstone_handling(self, client, auth_headers, mock_user, sample_tombstone):
        """Test that tombstones are properly handled and returned"""
        with patch('routes.v1.sync_route.get_current_user', return_value=mock_user), \
             patch.object(Form, 'objects') as mock_forms_query, \
             patch.object(TombstoneService, 'list_since') as mock_tombstone_service:
            
            # Setup mocks
            mock_forms_query.return_value.filter.return_value.only.return_value.limit.return_value = []
            mock_tombstone_service.return_value = [sample_tombstone]
            
            response = client.get('/api/internal/v1/sync', headers=auth_headers)
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            assert len(data['tombstones']) == 1
            tombstone = data['tombstones'][0]
            assert tombstone['entity_type'] == 'forms'
            assert tombstone['entity_id'] == 'form_456'
            assert 'deleted_at' in tombstone
    
    def test_get_delta_sync_response_structure(self, client, auth_headers, mock_user, sample_form):
        """Test that the response has the correct structure"""
        with patch('routes.v1.sync_route.get_current_user', return_value=mock_user), \
             patch.object(Form, 'objects') as mock_forms_query, \
             patch.object(TombstoneService, 'list_since') as mock_tombstone_service:
            
            # Setup mocks
            mock_forms_query.return_value.filter.return_value.only.return_value.limit.return_value = [sample_form]
            mock_tombstone_service.return_value = []
            
            response = client.get('/api/internal/v1/sync', headers=auth_headers)
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            # Check required fields
            required_fields = ['updated', 'tombstones', 'server_timestamp']
            for field in required_fields:
                assert field in data
            
            # Check updated item structure
            if data['updated']:
                updated_item = data['updated'][0]
                required_item_fields = ['id', 'orgId', 'projectId', 'name', 'description', 'schemaJson', 'lastSyncedAt', 'entityType']
                for field in required_item_fields:
                    assert field in updated_item
    
    def test_get_delta_sync_organization_scoping(self, client, auth_headers, mock_user):
        """Test that delta sync is properly scoped by organization"""
        with patch('routes.v1.sync_route.get_current_user', return_value=mock_user), \
             patch.object(Form, 'objects') as mock_forms_query:
            
            # Setup mock
            mock_forms_query.return_value.filter.return_value.only.return_value.limit.return_value = []
            
            response = client.get('/api/internal/v1/sync', headers=auth_headers)
            
            assert response.status_code == 200
            
            # Verify that the organization filter was applied
            mock_forms_query.assert_called_once()
            # The filter should be called with organization_id
            mock_forms_query.return_value.filter.assert_called()


class TestSyncStatusEndpoint:
    
    def test_get_sync_status(self, client, auth_headers, mock_user):
        """Test sync status endpoint"""
        with patch('routes.v1.sync_route.get_current_user', return_value=mock_user):
            response = client.get('/api/internal/v1/sync/status', headers=auth_headers)
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            # Check required fields
            required_fields = ['user_id', 'organization_id', 'last_sync', 'pending_responses', 
                             'pending_uploads', 'has_conflicts', 'server_time']
            for field in required_fields:
                assert field in data
            
            assert data['user_id'] == 'user_123'
            assert data['organization_id'] == 'org_456'
            assert 'server_time' in data
    
    def test_get_sync_status_server_error(self, client, auth_headers, mock_user):
        """Test sync status endpoint with server error"""
        with patch('routes.v1.sync_route.get_current_user') as mock_get_user:
            mock_get_user.side_effect = Exception("Auth error")
            
            response = client.get('/api/internal/v1/sync/status', headers=auth_headers)
            
            assert response.status_code == 500
            data = json.loads(response.data)
            assert 'error' in data


class TestSyncEndpointSecurity:
    
    def test_sync_endpoint_requires_auth(self, client):
        """Test that sync endpoints require authentication"""
        response = client.get('/api/internal/v1/sync')
        
        assert response.status_code == 401
    
    def test_sync_status_endpoint_requires_auth(self, client):
        """Test that sync status endpoint requires authentication"""
        response = client.get('/api/internal/v1/sync/status')
        
        assert response.status_code == 401
    
    def test_sync_endpoint_with_invalid_token(self, client):
        """Test sync endpoint with invalid token"""
        headers = {
            'Authorization': 'Bearer invalid-token',
            'Content-Type': 'application/json'
        }
        
        response = client.get('/api/internal/v1/sync', headers=headers)
        
        assert response.status_code == 422  # JWT validation error