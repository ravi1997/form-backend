import pytest
import json
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from flask import Flask
from routes.v1.analysis_route import analysis_bp
from flask_jwt_extended import JWTManager, create_access_token
from schemas.analysis import ExecutionMode

@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(analysis_bp, url_prefix='/api/v1')
    
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


class TestAnalysisRoutes:
    """Test suite for the analysis builder endpoints."""

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
        
        # Mock Project database lookup
        self.mock_project = MagicMock()
        self.mock_project.id = 'proj_1'
        self.mock_project.organization_id = 'org_456'
        self.mock_project.is_deleted = False
        
        self.project_objects_patch = patch('models.form.Project.objects')
        self.mock_project_query = self.project_objects_patch.start()
        self.mock_project_query.return_value.first.return_value = self.mock_project
        self.mock_project_query.filter.return_value.first.return_value = self.mock_project
        
        # Mock AccessControlService checks
        self.acs_patch = patch('services.access_control_service.AccessControlService.check_project_permission', return_value=True)
        self.acs_patch.start()
        
        yield
        
        self.user_objects_patch.stop()
        self.project_objects_patch.stop()
        self.acs_patch.stop()

    @patch('services.analysis_service.analysis_service.create_analysis')
    def test_create_analysis(self, mock_create, client, auth_headers):
        # Mock returned analysis model
        mock_analysis = MagicMock()
        mock_analysis.id = 'analysis_123'
        mock_analysis.to_dict.return_value = {
            'id': 'analysis_123',
            'project_id': 'proj_1',
            'name': 'Test Analysis',
            'graph': {'nodes': [], 'edges': []}
        }
        mock_create.return_value = mock_analysis

        payload = {
            'project_id': 'proj_1',
            'name': 'Test Analysis',
            'graph': {
                'nodes': [],
                'edges': []
            }
        }
        
        response = client.post('/api/v1/projects/proj_1/analyses', headers=auth_headers, json=payload)
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['data']['id'] == 'analysis_123'
        assert data['data']['name'] == 'Test Analysis'
        mock_create.assert_called_once()

    @patch('services.analysis_service.analysis_service.get_analysis')
    def test_get_analysis(self, mock_get, client, auth_headers):
        mock_analysis = MagicMock()
        mock_analysis.project_id = 'proj_1'
        mock_analysis.to_dict.return_value = {
            'id': 'analysis_123',
            'project_id': 'proj_1',
            'name': 'Test Get Analysis',
            'graph': {'nodes': [], 'edges': []}
        }
        mock_get.return_value = mock_analysis

        response = client.get('/api/v1/projects/proj_1/analyses/analysis_123', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['id'] == 'analysis_123'
        mock_get.assert_called_once_with('analysis_123', 'org_456')

    @patch('services.analysis_service.analysis_service.update_analysis')
    @patch('services.analysis_service.analysis_service.get_analysis')
    def test_update_analysis(self, mock_get, mock_update, client, auth_headers):
        mock_analysis = MagicMock()
        mock_analysis.project_id = 'proj_1'
        mock_get.return_value = mock_analysis

        mock_updated = MagicMock()
        mock_updated.to_dict.return_value = {
            'id': 'analysis_123',
            'project_id': 'proj_1',
            'name': 'Updated Name',
            'graph': {'nodes': [], 'edges': []}
        }
        mock_update.return_value = mock_updated

        payload = {
            'name': 'Updated Name'
        }

        response = client.put('/api/v1/projects/proj_1/analyses/analysis_123', headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['name'] == 'Updated Name'

    @patch('tasks.analysis_tasks.execute_analysis.delay')
    @patch('services.analysis_service.analysis_service.get_analysis')
    def test_execute_analysis(self, mock_get, mock_delay, client, auth_headers):
        mock_analysis = MagicMock()
        mock_analysis.project_id = 'proj_1'
        mock_get.return_value = mock_analysis

        mock_task = MagicMock()
        mock_task.id = 'task_run_123'
        mock_delay.return_value = mock_task

        response = client.post('/api/v1/projects/proj_1/analyses/analysis_123/execute', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['status'] == 'queued'
        assert data['data']['task_id'] == 'task_run_123'
        mock_delay.assert_called_once_with(
            analysis_id='analysis_123',
            organization_id='org_456',
            trigger='manual',
            triggered_by='user_123'
        )
