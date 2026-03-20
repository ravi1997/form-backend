from mongoengine import (
    EmbeddedDocumentField,
    StringField,
    ListField,
    DictField,
    BooleanField,
    ValidationError,
)
from models.enumerations import (
    FIELD_API_CALL_CHOICES,
    CONDITION_TYPE_CHOICES,
    LOGICAL_OPERATOR_CHOICES,
    CONDITION_SOURCE_TYPE_CHOICES,
    CONDITION_OPERATOR_CHOICES,
    COMPARISON_TYPE_CHOICES,
    TRIGGER_EVENT_CHOICES,
    TRIGGER_ACTION_CHOICES,
)
from models.base import BaseEmbeddedDocument


class Condition(BaseEmbeddedDocument):
    """
    Core logic engine for visibility and validation.
    Supports nested groups (AND/OR) and simple comparisons.
    """

    name = StringField()
    type = StringField(choices=CONDITION_TYPE_CHOICES, default="simple")
    logical_operator = StringField(choices=LOGICAL_OPERATOR_CHOICES, default="AND")
    conditions = ListField(EmbeddedDocumentField("self"))

    source_type = StringField(choices=CONDITION_SOURCE_TYPE_CHOICES, default="field")
    source_id = StringField()

    operator = StringField(choices=CONDITION_OPERATOR_CHOICES)

    comparison_type = StringField(choices=COMPARISON_TYPE_CHOICES, default="constant")
    comparison_value = DictField()
    custom_script = StringField()

    meta_data = DictField()
    is_debuggable = BooleanField(default=False)
    test_payload = DictField()
    expression_string = StringField()
    cross_validation_enabled = BooleanField(default=False)

    def clean(self):
        if self.type == "group" and not self.conditions:
            raise ValidationError(
                "Group conditions must specify at least one nested condition."
            )
        elif self.type == "simple":
            if not self.operator:
                raise ValidationError("Simple conditions require an operator.")
            if (
                self.comparison_type == "constant"
                and not self.comparison_value
                and self.operator not in ("is_empty", "is_not_empty")
            ):
                raise ValidationError(
                    "Constant comparisons require a comparison_value."
                )


class Trigger(BaseEmbeddedDocument):
    """
    Automated actions that fire based on events and conditions.
    Can be attached to Questions, Sections, Forms, or Projects.
    """

    name = StringField(required=True)
    event_type = StringField(choices=TRIGGER_EVENT_CHOICES, required=True)

    # Optional condition that must be true for the trigger to fire
    condition = EmbeddedDocumentField(Condition)

    # What happens when the trigger fires
    action_type = StringField(choices=TRIGGER_ACTION_CHOICES, required=True)

    # Configuration for the action (e.g., webhook URL, email template ID, field name to update)
    action_config = DictField()

    # Custom script to execute if action_type is 'execute_script'
    custom_script = StringField()

    is_active = BooleanField(default=True)
    order = StringField()  # Optional execution order
    meta_data = DictField()

    def clean(self):
        if self.action_type == "execute_script" and not self.custom_script:
            raise ValidationError(
                "Triggers using 'execute_script' action must provide a custom_script."
            )
        if self.action_type in ("webhook", "api_call") and not self.action_config:
            raise ValidationError(
                f"Triggers using '{self.action_type}' require action_config definitions."
            )


class LogicComponent(BaseEmbeddedDocument):
    """
    Reusable abstraction for dynamic behavior, visibility, and scripting.
    Used by both Sections and Questions.
    """

    meta = {"abstract": True}
    visibility_condition = EmbeddedDocumentField(Condition)
    is_disabled = BooleanField(default=False)
    on_change = StringField()
    field_api_call = StringField(choices=FIELD_API_CALL_CHOICES)
    custom_script = StringField()
    conditional_logic = DictField()
    action_config = DictField()
    triggers = ListField(EmbeddedDocumentField(Trigger))


class UIComponent(BaseEmbeddedDocument):
    """
    Reusable abstraction for visual and layout properties.
    """

    meta = {"abstract": True}
    style = DictField()
    visible_header = BooleanField(default=True)
    visible_name = StringField()
