"""
models/plugin.py
Plugin system models for extending form builder functionality.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument


class ComponentSchema(BaseEmbeddedDocument):
    """Plugin component schema definition."""

    plugin_id = StringField(required=True)
    plugin_version = StringField(required=True)
    concept_id = StringField(required=True)
    component_type = StringField(required=True)
    display_name = StringField(required=True)
    description = StringField()
    icon_path = StringField()
    
    # Form field composition
    composition = ListField(DictField(), default=list)
    
    # Properties configuration
    properties = ListField(DictField(), default=list)
    
    # Analysis node ports
    input_ports = ListField(DictField(), default=list)
    output_ports = ListField(DictField(), default=list)
    
    # Dashboard widget config
    widget_config = DictField(default=dict)
    
    # Preview and offline support
    preview_schema = DictField(default=dict)
    offline_support = BooleanField(default=False)
    
    created_at = DateTimeField()
    updated_at = DateTimeField()


class PluginVersion(BaseDocument, SoftDeleteMixin):
    """Plugin version tracking."""

    meta = {
        "collection": "plugin_versions",
        "indexes": [
            {"fields": ["plugin_id", "version"], "unique": True},
            "plugin_id",
            "status",
        ],
        "index_background": True,
    }

    plugin_id = StringField(required=True)
    version = StringField(required=True)
    manifest = DictField(required=True)
    files_path = StringField()
    status = StringField(choices=["active", "deprecated", "yanked"], default="active")
    released_at = DateTimeField()
    created_at = DateTimeField()


class Plugin(BaseDocument, SoftDeleteMixin):
    """Plugin main model for extending platform functionality."""

    meta = {
        "collection": "plugins",
        "indexes": [
            {"fields": ["plugin_id"], "unique": True},
            {"fields": ["organization_id", "name"]},
            "status",
            "created_at",
        ],
        "index_background": True,
    }

    plugin_id = StringField(required=True, unique=True)
    name = StringField(required=True)
    description = StringField()
    author = DictField()  # {name, email}
    version = StringField(required=True)
    manifest = DictField(required=True)
    status = StringField(choices=["active", "suspended", "unloaded"], default="active")
    
    # Plugin targeting
    concept_targets = ListField(StringField(), default=list)
    permissions = ListField(StringField(), default=list)
    
    # Installation tracking
    installed_at = DateTimeField()
    installed_by = ReferenceField("User", reverse_delete_rule=3)
    
    # Organization (null for system plugins)
    organization_id = StringField()
    
    created_at = DateTimeField()
    updated_at = DateTimeField()
    is_deleted = BooleanField(default=False)
    deleted_at = DateTimeField()


class ConceptRegistry(BaseDocument):
    """Registry for plugin concepts and component types."""

    meta = {
        "collection": "concept_registry",
        "indexes": [
            {"fields": ["concept_id"], "unique": True},
            "builder_type",
            "is_system",
        ],
        "index_background": True,
    }

    concept_id = StringField(required=True, unique=True)
    name = StringField(required=True)
    description = StringField()
    builder_type = StringField(required=True)  # form_builder, analysis_coder, dashboard_builder
    supported_component_types = ListField(StringField(), default=list)
    output_format = StringField()
    version_support = BooleanField(default=True)
    collaboration_support = BooleanField(default=False)
    is_system = BooleanField(default=False)
    created_at = DateTimeField()
    updated_at = DateTimeField()
    
    # System concepts have null organization_id
    organization_id = StringField()