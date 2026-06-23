import pytest
import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from flask import Flask
from routes.v1.dashboard_route import dashboard_bp, public_dashboard_bp
from services.dashboard_service import DashboardSchema
from services.dashboard_snapshot_service import SnapshotSchema
from flask_jwt_extended import JWTManager, create_access_token

@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(dashboard_bp, url_prefix='/api/v1/dashboards')
    app.register_blueprint(public_dashboard_bp, url_prefix='/api/v1/public/dashboards')
    
    # Add required JWT configuration
    app.config['JWT_SECRET_KEY'] = 'test-secret'
    app.config['JWT_TOKEN_LOCATION'] = ['headers']
    app.config['JWT_HEADER_NAME'] = 'Authorization'
    app.config['JWT_HEADER_TYPE'] = 'Bearer'
    
    JWTManager(app)
    
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers(app):
    with app.app_context():
        token = create_access_token(identity='user_123', additional_claims={'org_id': 'org_456'})
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }


@pytest.fixture
def mock_jwt_claims():
    return {
        'org_id': 'org_456',
        'sub': 'user_123',
        'identity': 'user_123'
    }


class TestDashboardRoutes:
    """Test suite for the new and updated dashboard endpoints."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self, mock_jwt_claims):
        # Mock User database lookup
        self.mock_user = MagicMock()
        self.mock_user.id = 'user_123'
        self.mock_user.organization_id = 'org_456'
        self.mock_user.role = 'org_admin'
        
        self.user_objects_patch = patch('models.identity.User.objects')
        self.mock_user_query = self.user_objects_patch.start()
        self.mock_user_query.return_value.first.return_value = self.mock_user
        
        # Mock Dashboard database lookup
        self.mock_db = MagicMock()
        self.mock_db.id = '507f1f77bcf86cd799439011'
        self.mock_db.name = 'Test DB'
        self.mock_db.title = 'Test DB'
        self.mock_db.organization_id = 'org_456'
        self.mock_db.project_id = 'proj_1'
        self.mock_db.widgets = []
        self.mock_db.filters = []
        self.mock_db.linked_analysis_ids = []
        
        self.db_objects_patch = patch('models.dashboard.Dashboard.objects')
        self.mock_db_query = self.db_objects_patch.start()
        self.mock_db_query.return_value.first.return_value = self.mock_db
        self.mock_db_query.get.return_value = self.mock_db
        
        # Mock AccessControlService checks
        self.acs_patch = patch('services.access_control_service.AccessControlService.check_dashboard_permission', return_value=True)
        self.acs_patch.start()
        
        yield
        
        self.user_objects_patch.stop()
        self.db_objects_patch.stop()
        self.acs_patch.stop()

    @patch('services.dashboard_service.DashboardService.list_dashboards')
    def test_list_dashboards(self, mock_list, client, auth_headers):
        # Setup mock return value
        mock_list.return_value = []
        
        response = client.get('/api/v1/dashboards/?project_id=proj_1', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'dashboards' in data['data']
        mock_list.assert_called_once_with(organization_id='org_456', project_id='proj_1')

    @patch('services.dashboard_service.DashboardService.get_dashboard')
    def test_get_dashboard_by_id(self, mock_get, client, auth_headers):
        dashboard_id = '507f1f77bcf86cd799439011' # Valid 24-character ObjectId
        
        # Pydantic schema return
        schema = DashboardSchema(
            id=dashboard_id,
            title='Test DB',
            slug='test-db',
            organization_id='org_456',
            project_id='proj_1',
            description='Desc',
            canvas={'width': 1920, 'height': 1080},
            widgets=[],
            filters=[]
        )
        mock_get.return_value = schema

        response = client.get(f'/api/v1/dashboards/{dashboard_id}', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['dashboard']['name'] == 'Test DB'
        mock_get.assert_called_once_with(dashboard_id, organization_id='org_456')

    @patch('services.dashboard_service.DashboardService.update_dashboard')
    def test_patch_dashboard(self, mock_update, client, auth_headers):
        dashboard_id = '507f1f77bcf86cd799439011'
        schema = DashboardSchema(
            id=dashboard_id,
            title='Updated Title',
            slug='updated-title',
            organization_id='org_456',
            canvas={'width': 1920, 'height': 1080},
            widgets=[],
            filters=[]
        )
        mock_update.return_value = schema

        response = client.patch(f'/api/v1/dashboards/{dashboard_id}', headers=auth_headers, json={'name': 'Updated Title'})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['name'] == 'Updated Title'
        mock_update.assert_called_once()

    @patch('services.dashboard_service.DashboardService.delete_dashboard')
    def test_delete_dashboard(self, mock_delete, client, auth_headers):
        dashboard_id = '507f1f77bcf86cd799439011'
        mock_delete.return_value = True

        response = client.delete(f'/api/v1/dashboards/{dashboard_id}', headers=auth_headers)
        assert response.status_code == 200
        mock_delete.assert_called_once_with(dashboard_id, organization_id='org_456', user_id='user_123')

    @patch('services.dashboard_service.DashboardService.enable_public_sharing')
    def test_enable_public_sharing(self, mock_enable, client, auth_headers):
        dashboard_id = '507f1f77bcf86cd799439011'
        mock_enable.return_value = {
            'dashboard_id': dashboard_id,
            'public_token': 'token123',
            'public_url': '/public/dashboard/token123',
            'is_public': True
        }

        response = client.post(f'/api/v1/dashboards/{dashboard_id}/public-token', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['public_token'] == 'token123'
        mock_enable.assert_called_once_with(dashboard_id, 'org_456', 'user_123')

    @patch('services.dashboard_service.DashboardService.disable_public_sharing')
    def test_disable_public_sharing(self, mock_disable, client, auth_headers):
        dashboard_id = '507f1f77bcf86cd799439011'
        mock_disable.return_value = True

        response = client.delete(f'/api/v1/dashboards/{dashboard_id}/public-token', headers=auth_headers)
        assert response.status_code == 200
        mock_disable.assert_called_once_with(dashboard_id, 'org_456', 'user_123')

    @patch('services.dashboard_snapshot_service.DashboardSnapshotService.create_snapshot')
    def test_create_snapshot(self, mock_create, client, auth_headers):
        dashboard_id = '507f1f77bcf86cd799439011'
        
        schema = SnapshotSchema(
            id='snap123',
            dashboard_id=dashboard_id,
            name='Test Snap',
            snapshot_data={},
            widget_states={},
            filter_states={},
            created_at=datetime.now(timezone.utc).isoformat(),
            is_public_snapshot=False
        )
        mock_create.return_value = schema

        response = client.post(f'/api/v1/dashboards/{dashboard_id}/snapshots', headers=auth_headers)
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['data']['snapshot']['id'] == 'snap123'

    @patch('services.dashboard_snapshot_service.DashboardSnapshotService.get_snapshot')
    def test_get_snapshot(self, mock_get, client, auth_headers):
        dashboard_id = '507f1f77bcf86cd799439011'
        snapshot_id = 'snap123'
        schema = SnapshotSchema(
            id=snapshot_id,
            dashboard_id=dashboard_id,
            name='Test Snap',
            snapshot_data={},
            widget_states={},
            filter_states={},
            created_at=datetime.now(timezone.utc).isoformat(),
            is_public_snapshot=False
        )
        mock_get.return_value = schema

        response = client.get(f'/api/v1/dashboards/{dashboard_id}/snapshots/{snapshot_id}', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['snapshot']['id'] == 'snap123'

    @patch('services.dashboard_snapshot_service.DashboardSnapshotService.delete_snapshot')
    def test_delete_snapshot(self, mock_delete, client, auth_headers):
        dashboard_id = '507f1f77bcf86cd799439011'
        snapshot_id = 'snap123'
        mock_delete.return_value = True

        response = client.delete(f'/api/v1/dashboards/{dashboard_id}/snapshots/{snapshot_id}', headers=auth_headers)
        assert response.status_code == 200
        mock_delete.assert_called_once_with(snapshot_id, 'org_456', 'user_123')
