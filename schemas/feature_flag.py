"""
schemas/feature_flag.py
Pydantic schemas for Feature Flag management.
"""

from typing import Optional, Dict
from pydantic import BaseModel, Field
from .base import BaseSchema

class FeatureFlagCreateSchema(BaseModel):
    flag_key: str = Field(..., description="Unique snake_case identifier for the feature flag")
    description: Optional[str] = Field(None, description="Detailed description of what this flag controls")
    is_enabled: bool = Field(False, description="Global default enablement status")
    scope: str = Field("global", description="Scope of the flag ('global' or 'org')")

class FeatureFlagUpdateSchema(BaseModel):
    is_enabled: bool = Field(..., description="Global default enablement status")

class FeatureFlagOrgOverrideSchema(BaseModel):
    is_enabled: bool = Field(..., description="Enablement status override for the specified organization")

class FeatureFlagSchema(BaseSchema):
    flag_key: str
    description: Optional[str] = None
    is_enabled: bool
    per_org_overrides: Dict[str, bool] = {}
    scope: str
