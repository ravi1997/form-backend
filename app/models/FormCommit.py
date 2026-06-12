from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class VisibilityRules(BaseModel):
    operator: str = Field(..., description="AND or OR")
    conditions: List[Dict[str, Any]] = Field(default_factory=list)

class Question(BaseModel):
    id: str = Field(..., description="Question UUID")
    type: str = Field(..., description="Component type")
    label: str = Field(..., description="Question label")
    description: Optional[str] = None
    required: bool = False
    properties: Dict[str, Any] = Field(default_factory=dict)
    visibility_rules: VisibilityRules = Field(default_factory=VisibilityRules)
    validation_rules: List[Dict[str, Any]] = Field(default_factory=list)
    calculations: List[Dict[str, Any]] = Field(default_factory=list)
    fetch_action: Optional[Dict[str, Any]] = None
    skip_logic: Optional[Dict[str, Any]] = None
    ui: Dict[str, Any] = Field(default_factory=dict)

class SubSection(BaseModel):
    id: str = Field(..., description="Sub-section UUID")
    title: str = Field(..., description="Sub-section title")
    repeatable: bool = False
    max_repeats: Optional[int] = None
    visibility_rules: VisibilityRules = Field(default_factory=VisibilityRules)
    questions: List[Question] = Field(default_factory=list)

class Section(BaseModel):
    id: str = Field(..., description="Section UUID")
    title: str = Field(..., description="Section title")
    description: Optional[str] = None
    repeatable: bool = False
    max_repeats: Optional[int] = None
    min_repeats: Optional[int] = None
    visibility_rules: VisibilityRules = Field(default_factory=VisibilityRules)
    sub_sections: List[SubSection] = Field(default_factory=list)

class FormUISchema(BaseModel):
    theme: Dict[str, Any] = Field(default_factory=dict)
    layout: str = Field(default="single_page")
    primary_color: Optional[str] = None
    font: Optional[str] = None
    logo_url: Optional[str] = None
    cover_page: Dict[str, Any] = Field(default_factory=dict)
    thank_you_page: Dict[str, Any] = Field(default_factory=dict)

class FormAccessConfig(BaseModel):
    type: str = Field(..., description="public, org, groups, users")
    allowed_org_ids: List[str] = Field(default_factory=list)
    allowed_group_ids: List[str] = Field(default_factory=list)
    allowed_user_ids: List[str] = Field(default_factory=list)
    allow_anonymous: bool = False

class FormSettings(BaseModel):
    expires_at: Optional[datetime] = None
    max_responses: Optional[int] = None
    allow_multiple_submissions: bool = False
    allow_draft_save: bool = False
    response_edit_policy: str = Field(default="no_edit")
    edit_time_window_hours: Optional[int] = None
    edit_allowed_roles: List[str] = Field(default_factory=list)
    require_login: bool = False

class WebhookConfig(BaseModel):
    url: str
    events: List[str]
    secret: Optional[str] = None

class FormCommit(BaseModel):
    form_id: str
    commit_id: str
    parent_ids: List[str] = Field(default_factory=list)
    author_id: str
    message: str
    branch: str
    tag: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    schema: Dict[str, Any] = Field(..., description="Full form schema snapshot")
    
    class Config:
        collection = "form_commits"

class Form(BaseModel):
    org_id: str
    project_id: str
    name: str
    description: Optional[str] = None
    branches: Dict[str, str] = Field(default_factory=lambda: {"main": ""})
    production_branch: str = Field(default="main")
    tags: Dict[str, str] = Field(default_factory=dict)
    template_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    created_by: str
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    
    class Config:
        collection = "forms"
