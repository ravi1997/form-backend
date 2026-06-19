"""
routes/v1/admin/__init__.py
Admin route registration.
"""

from flask import Blueprint

# Import all admin route blueprints
from .system_route import system_bp
from .api_key_route import api_key_bp
from .feature_flag_route import feature_flag_bp
from .org_management_route import org_management_bp
from .system_settings_route import system_settings_bp
from .task_route import admin_task_bp
from .webhook_route import webhook_admin_bp
from .ai_ops_route import ai_ops_bp
from .tenant_compliance_route import tenant_compliance_bp
from .compliance_route import compliance_bp

# Register all admin blueprints
def register_admin_blueprints(app):
    """Register all admin route blueprints."""
    app.register_blueprint(system_bp, url_prefix="/mahasangraha/api/v1/admin/system")
    app.register_blueprint(api_key_bp, url_prefix="/mahasangraha/api/v1/admin/api-keys")
    app.register_blueprint(feature_flag_bp, url_prefix="/mahasangraha/api/v1/admin/feature-flags")
    app.register_blueprint(org_management_bp, url_prefix="/mahasangraha/api/v1/admin/organizations")
    app.register_blueprint(system_settings_bp, url_prefix="/mahasangraha/api/v1/admin/settings")
    app.register_blueprint(admin_task_bp, url_prefix="/mahasangraha/api/v1/admin/tasks")
    app.register_blueprint(webhook_admin_bp, url_prefix="/mahasangraha/api/v1/admin/webhooks")
    app.register_blueprint(ai_ops_bp, url_prefix="/mahasangraha/api/v1/admin/ai-ops")
    app.register_blueprint(tenant_compliance_bp, url_prefix="/mahasangraha/api/v1/admin/tenant-compliance")
    app.register_blueprint(compliance_bp, url_prefix="/mahasangraha/api/v1/admin/compliance")