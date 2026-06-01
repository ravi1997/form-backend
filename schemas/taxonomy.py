from pydantic import Field
from typing import List, Optional
from .base import BaseEmbeddedSchema


class TaxonomyItemSchema(BaseEmbeddedSchema):
    category_name: str = Field(..., max_length=255)
    description: str = Field(..., max_length=1000)
    keywords: List[str] = Field(default_factory=list)
