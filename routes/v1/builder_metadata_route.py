from flasgger import swag_from
from flask import Blueprint
from flask_jwt_extended import jwt_required

from models.enumerations import (
    ACCESS_LEVEL_CHOICES,
    COMPARISON_TYPE_CHOICES,
    CONDITION_OPERATOR_CHOICES,
    CONDITION_SOURCE_TYPE_CHOICES,
    FIELD_API_CALL_CHOICES,
    FIELD_TYPE_CHOICES,
    LOGICAL_OPERATOR_CHOICES,
    PERMISSION_CHOICES,
    ROLE_CHOICES,
    TRIGGER_ACTION_CHOICES,
    TRIGGER_EVENT_CHOICES,
    UI_TYPE_CHOICES,
)
from utils.response_helper import success_response

builder_metadata_bp = Blueprint("builder_metadata", __name__)


def _builder_metadata_payload():
    return {
        "field_types": list(FIELD_TYPE_CHOICES),
        "ui_types": list(UI_TYPE_CHOICES),
        "condition": {
            "logical_operators": list(LOGICAL_OPERATOR_CHOICES),
            "source_types": list(CONDITION_SOURCE_TYPE_CHOICES),
            "operators": list(CONDITION_OPERATOR_CHOICES),
            "comparison_types": list(COMPARISON_TYPE_CHOICES),
        },
        "triggers": {
            "events": list(TRIGGER_EVENT_CHOICES),
            "actions": list(TRIGGER_ACTION_CHOICES),
            "field_api_calls": list(FIELD_API_CALL_CHOICES),
        },
        "access": {
            "levels": list(ACCESS_LEVEL_CHOICES),
            "permissions": list(PERMISSION_CHOICES),
            "roles": list(ROLE_CHOICES),
        },
        "validation": {
            "text": [
                "min_length",
                "max_length",
                "min_word_count",
                "max_word_count",
                "regex",
            ],
            "number": ["min_value", "max_value"],
            "date": [
                "date_min",
                "date_max",
                "disable_past_dates",
                "disable_future_dates",
                "disable_weekends",
            ],
            "file": ["allowed_file_types", "max_files", "max_file_size"],
            "selection": ["min_selection", "max_selection"],
        },
        "languages": [
            {"code": "en", "name": "English"},
            {"code": "hi", "name": "Hindi"},
        ],
    }


@builder_metadata_bp.route("/builder-metadata", methods=["GET"])
@swag_from(
    {"tags": ["Form"], "responses": {"200": {"description": "Builder metadata"}}}
)
@jwt_required()
def get_builder_metadata():
    return success_response(data=_builder_metadata_payload())
