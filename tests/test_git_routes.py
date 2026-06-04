import pytest
import uuid
from flask_jwt_extended import create_access_token
from models.Form import Form, Project
from models.FormCommit import FormCommit
from models.User import User


def test_git_api_routes(app, db_connection):
    from routes.v1.form import form_bp
    try:
        app.register_blueprint(
            form_bp, url_prefix="/mahasangraha/api/v1/projects/<project_id>/forms"
        )
    except AssertionError:
        pass
    # 1. Setup mock user and JWT
    with app.app_context():
        # Setup mock db user
        user = User(
            id=uuid.uuid4(),
            username="git_tester",
            email="git@test.com",
            user_type="employee",
            is_active=True,
            roles=["admin"],
            organization_id="org1",
        )
        user.save()

        token = create_access_token(
            identity=str(user.id),
            additional_claims={"roles": ["admin"], "organization_id": "org1"},
        )
        headers = {"Authorization": f"Bearer {token}"}

    client = app.test_client()

    # 2. Setup mock Project and Form in DB under org1
    project_id = str(uuid.uuid4())
    form_id = str(uuid.uuid4())

    project = Project(
        id=project_id,
        title="Git Test Project",
        organization_id="org1",
    ).save()

    form = Form(
        id=form_id,
        title="Git Form",
        slug="git-form",
        organization_id="org1",
        created_by=str(user.id),
    ).save()

    # 3. Call Create Commit API (HEAD should advance)
    url_commits = f"/mahasangraha/api/v1/projects/{project_id}/forms/{form_id}/commits"

    commit_payload_1 = {
        "message": "First Commit",
        "form_data": {
            "title": "Git Form",
            "sections": [
                {
                    "id": "sec-1",
                    "label": "Section One",
                    "questions": [{"id": "q-1", "type": "short_text", "label": "Name"}],
                }
            ],
        },
    }

    res_c1 = client.post(url_commits, json=commit_payload_1, headers=headers)
    assert res_c1.status_code == 200
    assert res_c1.json["success"] is True
    commit_1_id = res_c1.json["data"]["commit_id"]
    assert commit_1_id is not None

    # Check database head updated
    form.reload()
    assert str(form.head_commit_id) == commit_1_id

    # 4. Call List Commits API
    res_list = client.get(url_commits, headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json["data"]) == 1
    assert res_list.json["data"][0]["message"] == "First Commit"

    # 5. Create diverging branches for merge test
    # Mine commit (adds description)
    commit_payload_mine = {
        "message": "Mine branch changes",
        "form_data": {
            "title": "Git Form",
            "description": "Mine branch description",
            "sections": [
                {
                    "id": "sec-1",
                    "label": "Section One",
                    "questions": [{"id": "q-1", "type": "short_text", "label": "Name"}],
                }
            ],
        },
    }
    # Temporarily set form HEAD back to c1 to commit diverging change
    form = Form.objects(id=form_id).first()
    form.head_commit_id = uuid.UUID(commit_1_id)
    form.save()

    res_mine = client.post(url_commits, json=commit_payload_mine, headers=headers)
    commit_mine_id = res_mine.json["data"]["commit_id"]

    # Theirs commit (modifies title)
    commit_payload_theirs = {
        "message": "Theirs branch changes",
        "form_data": {
            "title": "Theirs branch title",
            "sections": [
                {
                    "id": "sec-1",
                    "label": "Section One",
                    "questions": [{"id": "q-1", "type": "short_text", "label": "Name"}],
                }
            ],
        },
    }
    # Reset form HEAD to c1 again to commit other branch
    form = Form.objects(id=form_id).first()
    form.head_commit_id = uuid.UUID(commit_1_id)
    form.save()

    res_theirs = client.post(url_commits, json=commit_payload_theirs, headers=headers)
    commit_theirs_id = res_theirs.json["data"]["commit_id"]

    # 6. Call Merge API (should auto-merge Mine & Theirs with no conflict)
    url_merge = f"/mahasangraha/api/v1/projects/{project_id}/forms/{form_id}/merge"
    merge_payload = {
        "theirs_commit_id": commit_theirs_id,
        "mine_commit_id": commit_mine_id,
    }

    res_merge = client.post(url_merge, json=merge_payload, headers=headers)
    assert res_merge.status_code == 200
    assert res_merge.json["data"]["status"] == "success"

    # Check merge result contains both modifications
    merged_data = res_merge.json["data"]["merged_data"]
    assert merged_data["title"] == "Theirs branch title"
    assert merged_data["description"] == "Mine branch description"
    assert len(merged_data["sections"][0]["questions"]) == 1
