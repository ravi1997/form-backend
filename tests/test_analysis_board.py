import pytest
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from models.Form import Project
from models.User import User
from models.AnalysisBoard import AnalysisBoard, AnalysisNode
from models.AnalysisRun import AnalysisRun, AnalysisResult
from services.analysis_board_service import AnalysisBoardService
from services.analytics_stream_service import AnalyticsStreamService
import config.settings as settings_module
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

    # 2. Circular dependency should be rejected
    node_a.inputs = [str(node_c.id)]
    with pytest.raises(Exception):
        analysis_service._resolve_topological_order([node_a, node_b, node_c])


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


def test_crud_endpoints(app, db_connection, redis_mock):
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
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            username="board_tester",
            email="board@test.com",
            user_type="employee",
            is_active=True,
            roles=["admin"],
            organization_id="org-test",
        ).save()

        user_claims = {"org_id": "org-test", "organization_id": "org-test", "roles": ["admin"]}
        token = create_access_token(identity=user_id, additional_claims=user_claims)
        headers = {"Authorization": f"Bearer {token}"}
        project_id = str(uuid.uuid4())

        client = app.test_client()

        # Mock DB queries and security checks
        mock_user = MagicMock()
        mock_user.id = user_id
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


def test_analytics_partitioned_writes_support_parallel_writers(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module.settings, "OLAP_ENGINE", "duckdb")
    monkeypatch.setattr(
        settings_module.settings, "DUCKDB_PATH", str(tmp_path / "analytics.duckdb")
    )

    service = AnalyticsStreamService()

    def write_event(idx: int):
        payload = {
            "response_id": f"resp-{idx}",
            "form_id": "form-1",
            "organization_id": "org-1",
            "timestamp": "2026-06-06T10:00:00Z",
            "data": {"field": idx},
        }
        service.process_submission_event(payload)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write_event, range(20)))

    parquet_files = list((Path(tmp_path) / "analytics_partitions").rglob("*.parquet"))
    assert len(parquet_files) == 20
    assert all("org-1" in str(path) for path in parquet_files)

    service.refresh_partition_view()
    trends = service.get_submission_trends("org-1", days=7)
    assert trends


def test_execute_board_persists_run_and_blocked_results(db_connection):
    service = AnalysisBoardService()
    board = AnalysisBoard(
        title="Persisted Board",
        project_id=str(uuid.uuid4()),
        organization_id="org-1",
        created_by="user-1",
        nodes=[
            AnalysisNode(
                id=uuid.uuid4(),
                title="Source Node",
                node_type="aggregation",
                function_id="SUM",
                target_form_id="form-1",
                target_field_id="age",
                inputs=[],
            ),
            AnalysisNode(
                id=uuid.uuid4(),
                title="Dependent Node",
                node_type="aspect_calculation",
                function_id="RATIO",
                target_form_id="",
                target_field_id="",
                inputs=[],
            ),
        ],
    ).save()
    board.nodes[1].inputs = [str(board.nodes[0].id)]
    board.save()

    with patch.object(service, "_run_db_aggregation", return_value=10.0), patch.object(
        service, "_execute_single_node", side_effect=[10.0, Exception("boom")]
    ):
        results = service.execute_board(str(board.id), "org-1", triggered_by="user-1")

    run = AnalysisRun.objects(analysis_id=str(board.id), organization_id="org-1").first()
    assert run is not None
    assert run.status == "failed"
    assert run.error_summary is not None

    stored_results = list(
        AnalysisResult.objects(run_id=str(run.id), organization_id="org-1").order_by(
            "created_at"
        )
    )
    assert len(stored_results) == 2
    assert results[str(board.nodes[0].id)] == 10.0
    assert results[str(board.nodes[1].id)]["status"] == "error"


def test_execute_board_marks_downstream_nodes_blocked(db_connection):
    service = AnalysisBoardService()
    upstream = AnalysisNode(
        id=uuid.uuid4(),
        title="Upstream",
        node_type="aggregation",
        function_id="SUM",
        target_form_id="form-1",
        target_field_id="age",
        inputs=[],
    )
    blocked = AnalysisNode(
        id=uuid.uuid4(),
        title="Blocked",
        node_type="aspect_calculation",
        function_id="RATIO",
        target_form_id="",
        target_field_id="",
        inputs=[str(upstream.id)],
    )
    board = AnalysisBoard(
        title="Blocked Board",
        project_id=str(uuid.uuid4()),
        organization_id="org-1",
        created_by="user-1",
        nodes=[upstream, blocked],
    ).save()

    with patch.object(service, "_execute_single_node", side_effect=[{"error": "boom"}]):
        results = service.execute_board(str(board.id), "org-1")

    assert results[str(upstream.id)]["error"] == "boom"
    assert results[str(blocked.id)]["status"] == "blocked"


def test_analysis_board_run_endpoints_return_history(app, db_connection):
    from flask_jwt_extended import create_access_token
    from routes.v1.analysis_board_route import analysis_board_bp

    try:
        app.register_blueprint(
            analysis_board_bp,
            url_prefix="/mahasangraha/api/v1/projects/<project_id>/analysis-boards",
        )
    except AssertionError:
        pass

    with app.app_context():
        user_id = str(uuid.uuid4())
        User(
            id=user_id,
            username="run_tester",
            email="run@test.com",
            user_type="employee",
            is_active=True,
            roles=["admin"],
            organization_id="org-1",
        ).save()
        token = create_access_token(
            identity=user_id,
            additional_claims={
                "org_id": "org-1",
                "organization_id": "org-1",
                "roles": ["admin"],
            },
        )
        headers = {"Authorization": f"Bearer {token}"}
        project_id = str(uuid.uuid4())

        board = AnalysisBoard(
            title="History Board",
            project_id=project_id,
            organization_id="org-1",
            created_by=user_id,
            nodes=[],
        ).save()
        Project(
            id=project_id,
            title="History Project",
            organization_id="org-1",
        ).save()
        run = AnalysisRun(
            analysis_id=str(board.id),
            organization_id="org-1",
            trigger="on_demand",
            triggered_by=user_id,
            status="completed",
        ).save()
        result = AnalysisResult(
            run_id=str(run.id),
            analysis_id=str(board.id),
            node_id="node-1",
            organization_id="org-1",
            output_type="value",
            data={"value": 42},
        ).save()

        client = app.test_client()
        with patch(
            "routes.v1.analysis_board_route.analysis_board_service.get_by_id",
            return_value=board,
        ):
            resp = client.get(
                f"/mahasangraha/api/v1/projects/{project_id}/analysis-boards/{board.id}/runs",
                headers=headers,
            )
            assert resp.status_code == 200
            assert resp.get_json()["data"]["total"] == 1

            resp = client.get(
                f"/mahasangraha/api/v1/projects/{project_id}/analysis-boards/{board.id}/runs/{run.id}",
                headers=headers,
            )
            assert resp.status_code == 200
            payload = resp.get_json()["data"]
            assert payload["run"]["id"] == str(run.id)
            assert payload["results"][0]["id"] == str(result.id)


def test_analysis_export_persistence(db_connection):
    from services.analysis_run_service import analysis_run_service

    export = analysis_run_service.create_export(
        analysis_id="analysis-1",
        run_id="run-1",
        organization_id="org-1",
        created_by="user-1",
        export_format="csv",
        node_ids=["node-1"],
        file_path="/tmp/export.csv",
        file_size_bytes=128,
        status="ready",
    )

    assert export.analysis_id == "analysis-1"
    assert export.run_id == "run-1"
    assert export.format == "csv"
    assert export.status == "ready"


def test_analysis_board_export_endpoints_return_created_export(app, db_connection):
    from flask_jwt_extended import create_access_token
    from routes.v1.analysis_board_route import analysis_board_bp

    try:
        app.register_blueprint(
            analysis_board_bp,
            url_prefix="/mahasangraha/api/v1/projects/<project_id>/analysis-boards",
        )
    except AssertionError:
        pass

    with app.app_context():
        user_id = str(uuid.uuid4())
        User(
            id=user_id,
            username="export_tester",
            email="export@test.com",
            user_type="employee",
            is_active=True,
            roles=["admin"],
            organization_id="org-1",
        ).save()
        token = create_access_token(
            identity=user_id,
            additional_claims={
                "org_id": "org-1",
                "organization_id": "org-1",
                "roles": ["admin"],
            },
        )
        headers = {"Authorization": f"Bearer {token}"}
        project_id = str(uuid.uuid4())
        Project(
            id=project_id,
            title="Export Project",
            organization_id="org-1",
        ).save()

        board = AnalysisBoard(
            title="Export Board",
            project_id=project_id,
            organization_id="org-1",
            created_by=user_id,
            nodes=[],
        ).save()

        client = app.test_client()
        with patch(
            "routes.v1.analysis_board_route.analysis_board_service.get_by_id",
            return_value=board,
        ):
            create_resp = client.post(
                f"/mahasangraha/api/v1/projects/{project_id}/analysis-boards/{board.id}/export",
                json={
                    "run_id": "run-1",
                    "format": "csv",
                    "node_ids": ["node-1"],
                    "file_path": "/tmp/export.csv",
                    "file_size_bytes": 256,
                    "status": "ready",
                },
                headers=headers,
            )
            assert create_resp.status_code == 201
            export_id = create_resp.get_json()["data"]["id"]

            get_resp = client.get(
                f"/mahasangraha/api/v1/projects/{project_id}/analysis-boards/{board.id}/export/{export_id}",
                headers=headers,
            )
            assert get_resp.status_code == 200
            assert get_resp.get_json()["data"]["format"] == "csv"


def test_analysis_board_export_downloads_ready_file(app, db_connection, tmp_path):
    from flask_jwt_extended import create_access_token
    from routes.v1.analysis_board_route import analysis_board_bp

    try:
        app.register_blueprint(
            analysis_board_bp,
            url_prefix="/mahasangraha/api/v1/projects/<project_id>/analysis-boards",
        )
    except AssertionError:
        pass

    with app.app_context():
        user_id = str(uuid.uuid4())
        User(
            id=user_id,
            username="download_tester",
            email="download@test.com",
            user_type="employee",
            is_active=True,
            roles=["admin"],
            organization_id="org-1",
        ).save()
        token = create_access_token(
            identity=user_id,
            additional_claims={
                "org_id": "org-1",
                "organization_id": "org-1",
                "roles": ["admin"],
            },
        )
        headers = {"Authorization": f"Bearer {token}"}
        project_id = str(uuid.uuid4())
        Project(
            id=project_id,
            title="Download Project",
            organization_id="org-1",
        ).save()

        board = AnalysisBoard(
            title="Download Board",
            project_id=project_id,
            organization_id="org-1",
            created_by=user_id,
            nodes=[],
        ).save()

        export_path = tmp_path / "analysis-export.csv"
        export_path.write_text("node_id,value\nnode-1,42\n", encoding="utf-8")

        from services.analysis_run_service import analysis_run_service

        export = analysis_run_service.create_export(
            analysis_id=str(board.id),
            run_id="run-1",
            organization_id="org-1",
            created_by=user_id,
            export_format="csv",
            node_ids=["node-1"],
            file_path=str(export_path),
            file_size_bytes=export_path.stat().st_size,
            status="ready",
        )

        client = app.test_client()
        with patch(
            "routes.v1.analysis_board_route.analysis_board_service.get_by_id",
            return_value=board,
        ):
            resp = client.get(
                f"/mahasangraha/api/v1/projects/{project_id}/analysis-boards/{board.id}/export/{export.id}/download",
                headers=headers,
            )
            assert resp.status_code == 200
            assert resp.data == export_path.read_bytes()
            assert resp.headers["Content-Disposition"].startswith("attachment;")
