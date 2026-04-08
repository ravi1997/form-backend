from flask import Blueprint
from flask import g, request

form_bp = Blueprint("form_bp", __name__)


@form_bp.url_value_preprocessor
def pull_project_id(endpoint, values):
    if not values:
        return
    project_id = values.pop("project_id", None)
    if project_id is not None:
        g.project_id = project_id

# Import routes to register them with the blueprint
from . import (
    form,
    responses,
    additional,
    advanced_responses,
    ai,
    analytics,
    anomaly,
    expire,
    export,
    files,
    helper,
    hooks,
    library,
    misc,
    nlp_search,
    permissions,
    summarization,
    translation,
    validation
)
