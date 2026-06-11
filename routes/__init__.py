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
from routes.v1.admin.system_settings_route import system_settings_bp
from routes.v1.admin.env_config_route import env_config_bp
from routes.v1.form.nlp_search import nlp_search_bp
from routes.v1.form.anomaly import anomaly_bp
from routes.v1.admin.system_route import system_bp
from routes.v1.admin.task_route import admin_task_bp
from routes.v1.admin.org_management_route import org_management_bp
from routes.v1.admin.feature_flag_route import feature_flag_bp
from routes.v1.admin.ai_ops_route import ai_ops_bp
from routes.v1.task_route import task_bp

from routes.v1.theme_route import theme_bp
from routes.v1.forms_misc_route import forms_misc_bp
from routes.v1.files_route import files_bp
# from routes.v1.report_route import report_bp  # TODO: Create this module or remove if not needed
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
    # app.register_blueprint(
    #     report_bp, url_prefix=f"{public_prefix}/projects/<project_id>/reports"
    # )

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
        system_settings_bp, url_prefix=f"{internal_prefix}/admin/system-settings"
    )
    app.register_blueprint(
        env_config_bp, url_prefix=f"{internal_prefix}/admin/env-config"
    )
    app.register_blueprint(system_bp, url_prefix=f"{internal_prefix}/system")
    app.register_blueprint(
        admin_task_bp, url_prefix=f"{internal_prefix}/admin/tasks"
    )
    app.register_blueprint(
        org_management_bp, url_prefix=f"{internal_prefix}/admin/orgs"
    )
    app.register_blueprint(
        feature_flag_bp, url_prefix=f"{internal_prefix}/admin/feature-flags"
    )
    app.register_blueprint(
        ai_ops_bp, url_prefix=f"{internal_prefix}/admin/ai-ops"
    )
    app.register_blueprint(task_bp, url_prefix=f"{public_prefix}/tasks")

    app.register_blueprint(theme_bp, url_prefix=f"{public_prefix}/themes")

    app.logger.info(
        "All blueprints registered successfully with normalized /api/v1/ and /api/internal/v1/ prefixes."
    )
