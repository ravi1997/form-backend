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
from routes.v1.report_route import report_bp
from routes.health import health_bp


def register_blueprints(app):
    # Base prefix for all routes to handle the gateway routing
    base_prefix = "/mahasangraha"

    # System health
    app.register_blueprint(health_bp, url_prefix=f"{base_prefix}/health")

    # Core Form Management - fully project scoped
    app.register_blueprint(
        form_bp, url_prefix=f"{base_prefix}/api/v1/projects/<project_id>/forms"
    )
    app.register_blueprint(project_bp, url_prefix=f"{base_prefix}/api/v1/projects")

    # New utility namespaces
    app.register_blueprint(forms_misc_bp, url_prefix=f"{base_prefix}/api/v1/forms")
    app.register_blueprint(files_bp, url_prefix=f"{base_prefix}/api/v1/files")

    # Translations mounted directly on translation prefix
    app.register_blueprint(
        translation_bp, url_prefix=f"{base_prefix}/api/v1/translations"
    )

    app.register_blueprint(library_bp, url_prefix=f"{base_prefix}/api/v1/custom-fields")
    app.register_blueprint(
        library_bp, url_prefix=f"{base_prefix}/api/v1/templates", name="form_templates"
    )
    app.register_blueprint(
        permissions_bp, url_prefix=f"{base_prefix}/api/v1/projects/<project_id>/forms"
    )
    app.register_blueprint(view_bp, url_prefix=f"{base_prefix}/api/v1/view")

    # Auth & AI
    app.register_blueprint(auth_bp, url_prefix=f"{base_prefix}/api/v1/auth")
    app.register_blueprint(ai_bp, url_prefix=f"{base_prefix}/api/v1/ai")
    app.register_blueprint(nlp_search_bp, url_prefix=f"{base_prefix}/api/v1/ai/search")

    # Dashboards & Analytics
    app.register_blueprint(dashboard_bp, url_prefix=f"{base_prefix}/api/v1/dashboards")
    app.register_blueprint(
        dashboard_settings_bp, url_prefix=f"{base_prefix}/api/v1/dashboard-settings"
    )
    app.register_blueprint(analytics_bp, url_prefix=f"{base_prefix}/api/v1/analytics")
    app.register_blueprint(
        anomaly_bp, url_prefix=f"{base_prefix}/api/v1/projects/<project_id>/forms"
    )
    app.register_blueprint(
        analysis_board_bp,
        url_prefix=f"{base_prefix}/api/v1/projects/<project_id>/analysis-boards",
    )
    app.register_blueprint(
        report_bp, url_prefix=f"{base_prefix}/api/v1/projects/<project_id>/reports"
    )

    # Workflows & Integrations
    app.register_blueprint(workflow_bp, url_prefix=f"{base_prefix}/api/v1/workflows")
    app.register_blueprint(webhooks_bp, url_prefix=f"{base_prefix}/api/v1/webhooks")
    app.register_blueprint(sms_bp, url_prefix=f"{base_prefix}/api/v1/sms")
    app.register_blueprint(external_api_bp, url_prefix=f"{base_prefix}/api/v1/external")

    # Mount advanced responses under project scope for project-bound operations
    app.register_blueprint(
        advanced_responses_bp,
        url_prefix=f"{base_prefix}/api/v1/projects/<project_id>/forms",
    )

    # User & System Management
    app.register_blueprint(user_bp, url_prefix=f"{base_prefix}/api/v1/user")
    app.register_blueprint(
        user_bp, url_prefix=f"{base_prefix}/api/v1/users", name="user_bp_plural"
    )
    app.register_blueprint(
        system_settings_bp, url_prefix=f"{base_prefix}/api/v1/admin/system-settings"
    )
    app.register_blueprint(
        env_config_bp, url_prefix=f"{base_prefix}/api/v1/admin/env-config"
    )
    app.register_blueprint(system_bp, url_prefix=f"{base_prefix}/api/v1/system")
    app.register_blueprint(
        admin_task_bp, url_prefix=f"{base_prefix}/api/v1/admin/tasks"
    )
    app.register_blueprint(
        org_management_bp, url_prefix=f"{base_prefix}/api/v1/admin/orgs"
    )
    app.register_blueprint(
        feature_flag_bp, url_prefix=f"{base_prefix}/api/v1/admin/feature-flags"
     )
    app.register_blueprint(
        ai_ops_bp, url_prefix=f"{base_prefix}/api/v1/admin/ai-ops"
    )
    app.register_blueprint(task_bp, url_prefix=f"{base_prefix}/api/v1/tasks")

    app.register_blueprint(theme_bp, url_prefix=f"{base_prefix}/api/v1/themes")

    app.logger.info(
        f"All blueprints registered successfully with normalized {base_prefix}/api/v1/ prefix."
    )
