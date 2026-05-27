import pytest
from unittest.mock import patch, MagicMock
from models.Form import Project
from models.AnalysisBoard import AnalysisBoard, AnalysisNode
from services.analysis_board_service import AnalysisBoardService
from schemas.analysis_board import (
    AnalysisBoardCreateSchema,
    AnalysisBoardUpdateSchema,
)
import uuid


@pytest.fixture
def analysis_service():
    return AnalysisBoardService()


def test_topological_sorting(analysis_service):
    """
    Test that topological sort resolves correct calculation sequence
    and detects circular dependencies.
    """
    node_a = AnalysisNode(
        id=uuid.uuid4(),
        title="Node A",
        node_type="aggregation",
        function_id="SUM",
        target_form_id=str(uuid.uuid4()),
        target_field_id="age",
        inputs=[],
    )
    node_b = AnalysisNode(
        id=uuid.uuid4(),
        title="Node B",
        node_type="aggregation",
        function_id="COUNT",
        target_form_id=str(uuid.uuid4()),
        target_field_id="age",
        inputs=[],
    )
    node_c = AnalysisNode(
        id=uuid.uuid4(),
        title="Node C",
        node_type="aspect_calculation",
        function_id="RATIO",
        target_form_id="",
        target_field_id="",
        inputs=[str(node_a.id), str(node_b.id)],
    )

    # 1. Normal DAG
    order = analysis_service._resolve_topological_order([node_a, node_b, node_c])
    assert len(order) == 3
    assert order.index(str(node_c.id)) > order.index(str(node_a.id))
    assert order.index(str(node_c.id)) > order.index(str(node_b.id))

    # 2. Circular dependency fallback
    node_a.inputs = [str(node_c.id)]
    circular_order = analysis_service._resolve_topological_order(
        [node_a, node_b, node_c]
    )
    assert len(circular_order) == 3


def test_execute_aspect_nodes(analysis_service):
    """
    Tests mathematical calculation logic on nodes with inputs.
    """
    node = AnalysisNode(
        id=uuid.uuid4(),
        title="Ratio Node",
        node_type="aspect_calculation",
        function_id="RATIO",
        target_form_id="",
        target_field_id="",
        inputs=[str(uuid.uuid4()), str(uuid.uuid4())],
    )

    # Mock inputs results
    resolved_parent_results = {str(node.inputs[0]): 100.0, str(node.inputs[1]): 5.0}

    res = analysis_service._execute_single_node(
        node, resolved_parent_results, "org-123"
    )
    assert res == 20.0

    # Div by zero should gracefully return None
    resolved_parent_results[str(node.inputs[1])] = 0.0
    res = analysis_service._execute_single_node(
        node, resolved_parent_results, "org-123"
    )
    assert res is None


def test_crud_endpoints(app):
    """
    Tests CRUD routing endpoints on /api/v1/projects/<project_id>/analysis-boards
    """
    from flask_jwt_extended import create_access_token
    from routes.v1.analysis_board_route import analysis_board_bp

    # Register blueprint if not already registered
    try:
        app.register_blueprint(
            analysis_board_bp,
            url_prefix="/mahasangraha/api/v1/projects/<project_id>/analysis-boards",
        )
    except AssertionError:
        pass  # already registered

    with app.app_context():
        user_claims = {"org_id": "org-test", "roles": ["admin"]}
        token = create_access_token(identity="user-test", additional_claims=user_claims)
        headers = {"Authorization": f"Bearer {token}"}
        project_id = str(uuid.uuid4())

        client = app.test_client()

        # Mock DB queries and security checks
        mock_user = MagicMock()
        mock_user.id = "user-test"
        mock_user.organization_id = "org-test"
        mock_user.roles = ["admin"]

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.organization_id = "org-test"

        mock_board = MagicMock()
        mock_board.id = "board-123"
        mock_board.title = "AdHoc Board"
        mock_board.project_id = project_id
        mock_board.organization_id = "org-test"
        mock_board.model_dump.return_value = {
            "id": "board-123",
            "title": "AdHoc Board",
            "project_id": project_id,
            "organization_id": "org-test",
            "nodes": [],
        }

        # Setup mock return values for listing
        mock_paginated_result = MagicMock()
        mock_paginated_result.to_dict.return_value = {
            "items": [mock_board.model_dump()],
            "total": 1,
            "page": 1,
            "page_size": 50,
            "has_next": False,
            "success": True,
        }

        # Perform mocked calls
        with patch(
            "utils.security_helpers.get_current_user", return_value=mock_user
        ), patch.object(Project, "objects") as mock_project_objects, patch(
            "routes.v1.analysis_board_route.analysis_board_service"
        ) as mock_service, patch(
            "utils.security_helpers.AccessControlService.check_project_permission",
            return_value=True,
        ):

            # Setup mock project query
            mock_project_query = MagicMock()
            mock_project_query.first.return_value = mock_project
            mock_project_objects.return_value = mock_project_query

            # Setup mock service calls
            mock_service.create.return_value = mock_board
            mock_service.get_by_id.return_value = mock_board
            mock_service.update.return_value = mock_board
            mock_service.list_paginated.return_value = mock_paginated_result

            # 1. Create Board (POST)
            payload = {
                "title": "AdHoc Board",
                "description": "Calculates correlation metric",
                "nodes": [],
            }
            resp = client.post(
                f"/mahasangraha/api/v1/projects/{project_id}/analysis-boards/",
                json=payload,
                headers=headers,
            )
            assert resp.status_code == 201
            assert resp.get_json()["data"]["title"] == "AdHoc Board"

            # 2. Get Board by ID (GET)
            resp = client.get(
                f"/mahasangraha/api/v1/projects/{project_id}/analysis-boards/board-123",
                headers=headers,
            )
            assert resp.status_code == 200
            assert resp.get_json()["data"]["title"] == "AdHoc Board"

            # 3. Update Board (PUT)
            update_payload = {"title": "Updated Board Title"}
            mock_board.title = "Updated Board Title"
            mock_board.model_dump.return_value["title"] = "Updated Board Title"

            resp = client.put(
                f"/mahasangraha/api/v1/projects/{project_id}/analysis-boards/board-123",
                json=update_payload,
                headers=headers,
            )
            assert resp.status_code == 200
            assert resp.get_json()["data"]["title"] == "Updated Board Title"

            # 4. List Boards (GET)
            resp = client.get(
                f"/mahasangraha/api/v1/projects/{project_id}/analysis-boards/",
                headers=headers,
            )
            assert resp.status_code == 200
            assert resp.get_json()["data"]["total"] == 1

            # 5. Delete Board (DELETE)
            resp = client.delete(
                f"/mahasangraha/api/v1/projects/{project_id}/analysis-boards/board-123",
                headers=headers,
            )
            assert resp.status_code == 200
            assert resp.get_json()["message"] == "Analysis Board deleted"
