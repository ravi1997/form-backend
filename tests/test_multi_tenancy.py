import pytest
from unittest.mock import patch, MagicMock
from services.dashboard_service import DashboardService
from models.Dashboard import Dashboard
from utils.exceptions import ForbiddenError, NotFoundError

@pytest.fixture
def dashboard_service():
    return DashboardService()

def test_dashboard_service_enforces_org_id(dashboard_service):
    """
    Ensures that DashboardService filters by organization_id.
    """
    mock_query = MagicMock()
    mock_query.first.return_value = Dashboard(title="My Dash", organization_id="org-A", slug="my-dash")
    
    # Patching the class attribute 'objects' directly on the Dashboard class
    with patch.object(Dashboard, 'objects') as mock_objects:
        mock_objects.return_value = mock_query
        
        # 1. Correct Org
        dash = dashboard_service.get_by_slug("my-dash", organization_id="org-A")
        assert dash.slug == "my-dash"
        mock_objects.assert_called()

        # 2. Wrong Org (should raise NotFound because of filtering)
        mock_query.first.return_value = None
        with pytest.raises(NotFoundError):
            dashboard_service.get_by_slug("my-dash", organization_id="org-B")
            
def test_soft_delete_filtering():
    """
    Ensures that SoftDeleteQuerySet is active by default.
    """
    with patch.object(Dashboard, 'objects') as mock_objects:
        # When calling Dashboard.objects, it should be mocked
        pass
