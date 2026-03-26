from flask import Blueprint

form_bp = Blueprint("form_bp", __name__)

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
