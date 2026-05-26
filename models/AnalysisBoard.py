import uuid
from datetime import datetime, timezone
from mongoengine import (
    StringField,
    ListField,
    DictField,
    EmbeddedDocument,
    EmbeddedDocumentField,
    UUIDField,
    FloatField,
)
from models.base import BaseDocument, SoftDeleteMixin


class AnalysisNode(EmbeddedDocument):
    """
    Represents a single visual calculation node inside an Analysis Board.
    Each node performs a predefined arithmetic, statistical, or semantic function.
    """
    id = UUIDField(primary_key=True, default=uuid.uuid4, binary=False)
    title = StringField(required=True)
    node_type = StringField(required=True, default="aggregation")  # "aggregation", "aspect_calculation", "filter"
    function_id = StringField(required=True)  # SUM, COUNT, AVERAGE, STD_DEV, CORRELATION, etc.
    
    # Data source selectors
    target_form_id = StringField(required=True)
    target_field_id = StringField(required=True)  # question variable name
    secondary_field_id = StringField()  # secondary field for ratios/correlation

    # Filters applied strictly to this calculation aspect
    filters = DictField(default=dict)

    # UI coordinates for drag and drop canvas
    position_x = FloatField(default=0.0)
    position_y = FloatField(default=0.0)

    # Linkage inputs - stores UUIDs of parent node dependencies
    inputs = ListField(UUIDField(), default=list)

    # General specific parameters
    config = DictField(default=dict)


class AnalysisBoard(BaseDocument, SoftDeleteMixin):
    """
    Multi-tenant mathematical canvas designed to build custom analysis calculations
    by linking separate calculation aspect blocks together.
    """
    meta = {
        "collection": "analysis_boards",
        "indexes": ["organization_id", "project_id"],
        "index_background": True,
    }
    
    title = StringField(required=True)
    project_id = StringField(required=True)
    organization_id = StringField(required=True)
    description = StringField()
    
    nodes = ListField(EmbeddedDocumentField(AnalysisNode), default=list)
    created_by = StringField(required=True)
