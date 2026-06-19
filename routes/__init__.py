from routes.v1.form import form_bp
from routes.v1.project_route import project_bp
from routes.v1.auth_route import auth_bp
from routes.v1.view_route import view_bp
from routes.v1.user_route import user_bp
from routes.v1.form.ai import ai_bp
from routes.v1.form.library import library_bp
from routes.v1.form.permissions import permissions_bp
from routes.v1.dashboard_route import dashboard_bp
from routes.v1.dashboard_settings_route import dashboard_settings_bp
from routes.v1.analysis_board_route import analysis_board_bp
from routes.v1.workflow_route import workflow_bp
from routes.v1.webhooks import webhooks_bp
from routes.v1.form.translation import translation_bp
from routes.v1.sms_route import sms_bp
from routes.v1.analytics_route import analytics_bp
from routes.v1.external_api_route import external_api_bp
from routes.v1.form.advanced_responses import advanced_responses_bp
from routes.v1.admin.env_config_route import env_config_bp
from routes.v1.form.nlp_search import nlp_search_bp
from routes.v1.form.anomaly import anomaly_bp
from routes.v1.task_route import task_bp
from routes.v1.admin import register_admin_blueprints
from routes.v1.notification_route import notification_bp
from routes.v1.oauth_route import oauth_bp
from routes.v1.sync_route import sync_bp

from routes.v1.theme_route import theme_bp
from routes.v1.forms_misc_route import forms_misc_bp
from routes.v1.files_route import files_bp
from routes.health import health_bp


def register_blueprints(app):
    # Public and internal API prefixes follow the CONTEXT.md routing structure.
    public_prefix = "/api/v1"
    internal_prefix = "/api/internal/v1"

    # System health stays on the public API surface.
    app.register_blueprint(health_bp, url_prefix=f"{public_prefix}/health")

    # Core Form Management - fully project scoped
    app.register_blueprint(
        form_bp, url_prefix=f"{public_prefix}/projects/<project_id>/forms"
    )
    app.register_blueprint(project_bp, url_prefix=f"{public_prefix}/projects")

    # New utility namespaces
    app.register_blueprint(forms_misc_bp, url_prefix=f"{public_prefix}/forms")
    app.register_blueprint(files_bp, url_prefix=f"{public_prefix}/files")

    # Translations mounted directly on translation prefix
    app.register_blueprint(translation_bp, url_prefix=f"{public_prefix}/translations")

    app.register_blueprint(library_bp, url_prefix=f"{public_prefix}/custom-fields")
    app.register_blueprint(
        library_bp, url_prefix=f"{public_prefix}/templates", name="form_templates"
    )
    app.register_blueprint(
        permissions_bp, url_prefix=f"{public_prefix}/projects/<project_id>/forms"
    )
    app.register_blueprint(view_bp, url_prefix=f"{public_prefix}/view")

    # Auth & AI
    app.register_blueprint(auth_bp, url_prefix=f"{public_prefix}/auth")
    app.register_blueprint(auth_bp, url_prefix="/api/auth", name="auth_bp_compat")
    app.register_blueprint(ai_bp, url_prefix=f"{public_prefix}/ai")
    app.register_blueprint(nlp_search_bp, url_prefix=f"{public_prefix}/ai/search")

    # Dashboards & Analytics
    app.register_blueprint(dashboard_bp, url_prefix=f"{public_prefix}/dashboards")
    app.register_blueprint(
        dashboard_bp,
        url_prefix="/api/internal/v1/dashboards",
        name="dashboard_bp_compat",
    )
    app.register_blueprint(
        dashboard_settings_bp, url_prefix=f"{public_prefix}/dashboard-settings"
    )
    app.register_blueprint(analytics_bp, url_prefix=f"{public_prefix}/analytics")
    app.register_blueprint(
        anomaly_bp, url_prefix=f"{public_prefix}/projects/<project_id>/forms"
    )
    app.register_blueprint(
        analysis_board_bp,
        url_prefix=f"{public_prefix}/projects/<project_id>/analysis-boards",
    )

    # Workflows & Integrations
    app.register_blueprint(workflow_bp, url_prefix=f"{public_prefix}/workflows")
    app.register_blueprint(webhooks_bp, url_prefix=f"{public_prefix}/webhooks")
    app.register_blueprint(sms_bp, url_prefix=f"{public_prefix}/sms")
    app.register_blueprint(external_api_bp, url_prefix=f"{public_prefix}/external")

    # Mount advanced responses under project scope for project-bound operations
    app.register_blueprint(
        advanced_responses_bp,
        url_prefix=f"{public_prefix}/projects/<project_id>/forms",
    )

    # User & System Management
    app.register_blueprint(user_bp, url_prefix=f"{public_prefix}/user")
    app.register_blueprint(
        user_bp, url_prefix=f"{public_prefix}/users", name="user_bp_plural"
    )
    app.register_blueprint(
        env_config_bp, url_prefix=f"{internal_prefix}/admin/env-config"
    )
    app.register_blueprint(task_bp, url_prefix=f"{public_prefix}/tasks")

    # Notifications
    app.register_blueprint(notification_bp, url_prefix=f"{public_prefix}/notifications")
    
    # OAuth and API Keys
    app.register_blueprint(oauth_bp, url_prefix=f"{public_prefix}/oauth")
    app.register_blueprint(oauth_bp, url_prefix="/mahasangraha/api/v1/oauth", name="oauth_bp_mahasangraha")

    app.register_blueprint(theme_bp, url_prefix=f"{public_prefix}/themes")
    
    # Offline sync endpoints
    app.register_blueprint(sync_bp, url_prefix=f"{internal_prefix}/sync")
    
    # Register all admin blueprints
    register_admin_blueprints(app)

    app.logger.info(
        "All blueprints registered successfully with normalized /api/v1/ and /api/internal/v1/ prefixes."
    )
