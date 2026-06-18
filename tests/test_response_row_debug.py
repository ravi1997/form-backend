import os
import uuid

import mongoengine
from bson import json_util
from bson.binary import Binary, UuidRepresentation

from models.form import Form, Project
from models.response import FormResponse


def _uuid_from_value(value):
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "id"):
        return str(value.id)
    try:
        return str(uuid.UUID(str(value)))
    except Exception:
        return str(value)


def _expand_response(response):
    expanded = response.to_mongo().to_dict()

    form_id = _uuid_from_value(response._data.get("form"))
    project_id = _uuid_from_value(response._data.get("project"))

    if form_id:
        form_doc = Form.objects(id=form_id).first()
        if form_doc:
            expanded["form_full"] = form_doc.to_mongo().to_dict()

    if project_id:
        project_doc = Project.objects(id=project_id).first()
        if project_doc:
            expanded["project_full"] = project_doc.to_mongo().to_dict()

    return expanded


def _stringify_uuids(value):
    if isinstance(value, dict):
        return {k: _stringify_uuids(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_stringify_uuids(item) for item in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def print_expanded_form_response_rows():
    """
    Helper for manually inspecting stored form response rows using MongoEngine.
    Run with:
        pytest -s tests/test_response_row_debug.py
    """
    uri = os.environ["MONGODB_URI"]
    mongoengine.connect(db="test_db", host=uri)

    target_form_id = "49a25ba1-96e5-4604-952d-44af6053c4d0"
    target_question_id = "full_name"
    target_value = "Alice Smith"
    target_form_binary = Binary.from_uuid(
        uuid.UUID(target_form_id),
        uuid_representation=UuidRepresentation.PYTHON_LEGACY,
    )

    try:
        responses = (
            FormResponse.objects(
                __raw__={
                    "organization_id": "org_001",
                    "is_deleted": False,
                    "form": target_form_binary,
                    f"data.{target_question_id}": target_value,
                }
            )
            .order_by("submitted_at")
            .limit(100)
        )
        print("query done")
        for response in responses:
            print(
                json_util.dumps(_stringify_uuids(_expand_response(response)), indent=2)
            )
            print("---")
    finally:
        mongoengine.disconnect()


if __name__ == "__main__":
    print_expanded_form_response_rows()
