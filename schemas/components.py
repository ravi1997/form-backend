from pydantic import Field
from typing import Optional, List, Dict, Any, ForwardRef, Literal
from .base import BaseEmbeddedSchema

ConditionSchemaStruct = ForwardRef("ConditionSchemaStruct")


class ConditionSchemaStruct(BaseEmbeddedSchema):
    name: Optional[str] = None
    type: Literal["simple", "group"] = "simple"
    logical_operator: Literal["AND", "OR", "NOT", "NOR", "NAND"] = "AND"
    conditions: List["ConditionSchemaStruct"] = Field(default_factory=list)

    source_type: Literal[
        "field", "hidden_field", "url_param", "user_info", "calculated_value"
    ] = "field"
    source_id: Optional[str] = None
    operator: Optional[
        Literal[
            "equals",
            "not_equals",
            "greater_than",
            "less_than",
            "greater_than_equals",
            "less_than_equals",
            "contains",
            "not_contains",
            "starts_with",
            "ends_with",
            "is_empty",
            "is_not_empty",
            "in_list",
            "not_in_list",
            "matches_regex",
            "between",
            "is_checked",
        ]
    ] = None

    comparison_type: Literal[
        "constant", "field", "url_param", "user_info", "calculation"
    ] = "constant"
    comparison_value: Optional[Dict[str, Any]] = None
    custom_script: Optional[str] = None

    meta_data: Optional[Dict[str, Any]] = None
    is_debuggable: bool = False
    test_payload: Optional[Dict[str, Any]] = None
    expression_string: Optional[str] = None
    cross_validation_enabled: bool = False


ConditionSchemaStruct.model_rebuild()
ConditionSchema = ConditionSchemaStruct


class TriggerSchema(BaseEmbeddedSchema):
    name: str = Field(..., max_length=255)
    event_type: Literal[
        "on_load",
        "on_submit",
        "on_change",
        "on_status_change",
        "on_validate",
        "on_approval_step",
        "on_creation",
    ]
    condition: Optional[ConditionSchema] = None
    action_type: Literal[
        "webhook",
        "email",
        "sms",
        "notification",
        "update_field",
        "execute_script",
        "hide_show",
        "enable_disable",
        "validation_error",
        "calculation",
        "api_call",
    ]
    action_config: Optional[Dict[str, Any]] = None
    custom_script: Optional[str] = None
    is_active: bool = True
    order: Optional[str] = None
    meta_data: Optional[Dict[str, Any]] = None


class LogicComponentSchema(BaseEmbeddedSchema):
    visibility_condition: Optional[ConditionSchema] = None
    is_disabled: bool = False
    on_change: Optional[str] = None
    field_api_call: Optional[
        Literal["uhid", "employee_id", "form", "otp", "custom"]
    ] = None
    custom_script: Optional[str] = None
    conditional_logic: Optional[Dict[str, Any]] = None
    action_config: Optional[Dict[str, Any]] = None
    triggers: List[TriggerSchema] = Field(default_factory=list)


class UIComponentSchema(BaseEmbeddedSchema):
    style: Optional[Dict[str, Any]] = None
    visible_header: bool = True
    visible_name: Optional[str] = None
