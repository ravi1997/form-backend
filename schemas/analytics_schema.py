from pydantic import BaseModel
from typing import Dict, Any

class AnalyticsStateSchema(BaseModel):
    """
    [Phase 12: Polyglot Persistence Readiness]
    Defines the structural format for routing form responses downstream via 
    Change Data Capture (CDC) or Redpanda/Kafka streams. 
    This schema ensures that dynamic form fields ($group mechanics) are flattened 
    identically so ClickHouse or Snowflake consumers can reliably parse mutations.
    """
    event_timestamp: float
    tenant_id: str
    form_id: str
    response_id: str
    # Pre-flattened representation of dynamic schema geometries
    flattened_fields: Dict[str, Any]
    action_type: str # "inserted", "updated", "soft_deleted"
