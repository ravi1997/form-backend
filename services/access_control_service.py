from typing import Optional, List, Literal
from models.User import User
from models.Response import FormResponse
from models.Dashboard import Dashboard
from models.Form import Form, Project
from models.AccessControl import ResourceAccessControl
from logger.unified_logger import app_logger
from utils.sensitive_data_redaction import safe_log_info


class AccessControlService:
    """
    Unified access control service consolidating RBAC, ABAC, and public access logic.
    Evaluates access in this order:
    1. Public access check (bypasses org_id for is_public resources)
    2. Global RBAC: Superadmin/Admin bypass
    3. Resource ownership: Creator/Owner checks
    4. Resource-level ACLs: editors/viewers/submitters arrays
    5. ABAC: AccessPolicy documents for fine-grained conditions
    """

    @staticmethod
    def check_form_permission(
        user: Optional[User],
        form: Form,
        action: Literal[
            "view",
            "edit",
            "submit",
            "view_responses",
            "edit_responses",
            "delete_responses",
            "edit_design",
            "manage_access",
            "view_audit",
            "delete_form",
        ],
    ) -> bool:
        """
        Check if a user has permission to perform an action on a form.
        """
        if not user or not form:
            return False

        user_id_str = str(user.id)
        user_roles = getattr(user, "roles", []) or []
        user_dept = getattr(user, "department", None)

        safe_log_info(
            app_logger,
            "Checking form permission '%s' for user %s on form %s",
            action,
            user_id_str,
            str(form.id),
        )

        # 1. PUBLIC ACCESS: View/submit allowed for public forms regardless of organization
        if form.is_public and action in ("view", "submit"):
            safe_log_info(
                app_logger,
                "Public %s permission granted for user %s on public form %s",
                action,
                user_id_str,
                str(form.id),
            )
            return True

        # 2. Enforce tenant isolation for non-public forms
        if not form.is_public and getattr(user, "organization_id", None) != getattr(
            form, "organization_id", None
        ):
            safe_log_info(
                app_logger,
                "Tenant mismatch: user org %s != form org %s",
                getattr(user, "organization_id", None),
                getattr(form, "organization_id", None),
            )
            return False

        # 3. Superadmin always has all permissions
        if "superadmin" in user_roles:
            safe_log_info(
                app_logger, "User %s is superadmin, permission granted", user_id_str
            )
            return True

        # 4. Creator always has all permissions
        if str(form.created_by) == user_id_str:
            safe_log_info(
                app_logger, "User %s is creator, permission granted", user_id_str
            )
            return True

        # 5. Helper to check if user or their roles are in a list
        def is_in_list(target_list: Optional[List[str]]) -> bool:
            if not target_list:
                return False
            if user_id_str in target_list:
                return True
            for role in user_roles:
                if role in target_list:
                    return True
            return False

        # 6. Access Policy / Form ACLs
        policy = (
            form.access_policy
            if hasattr(form, "access_policy") and form.access_policy
            else None
        )

        # VIEW FORM
        if action == "view":
            if is_in_list(form.viewers) or is_in_list(form.editors) or form.is_public:
                safe_log_info(
                    app_logger,
                    "View permission granted for user %s via viewers/editors/public",
                    user_id_str,
                )
                return True
            if policy:
                if policy.form_visibility == "public":
                    safe_log_info(
                        app_logger,
                        "View permission granted for user %s via public policy",
                        user_id_str,
                    )
                    return True
                if policy.form_visibility == "restricted":
                    if user_dept and user_dept in (policy.allowed_departments or []):
                        safe_log_info(
                            app_logger,
                            "View permission granted for user %s via department %s",
                            user_id_str,
                            user_dept,
                        )
                        return True
                    if is_in_list(policy.can_view_responses):
                        safe_log_info(
                            app_logger,
                            "View permission granted for user %s via can_view_responses list",
                            user_id_str,
                        )
                        return True
            safe_log_info(app_logger, "View permission denied for user %s", user_id_str)
            return False

        # SUBMIT FORM
        if action == "submit":
            # Allow anyone in same organization to submit by default
            # Public forms are handled at step 1
            safe_log_info(
                app_logger,
                "Submit permission granted for user %s (org match)",
                user_id_str,
            )
            return True

        # EDIT DESIGN / CREATE VERSIONS
        if action in ("edit", "edit_design"):
            if is_in_list(form.editors):
                safe_log_info(
                    app_logger,
                    "Edit permission granted for user %s via editors list",
                    user_id_str,
                )
                return True
            if policy and is_in_list(policy.can_edit_design):
                safe_log_info(
                    app_logger,
                    "Edit permission granted for user %s via policy can_edit_design",
                    user_id_str,
                )
                return True
            safe_log_info(app_logger, "Edit permission denied for user %s", user_id_str)
            return False

        # MANAGE ACCESS
        if action == "manage_access":
            if "admin" in user_roles:
                safe_log_info(
                    app_logger,
                    "Manage access permission granted for user %s via admin role",
                    user_id_str,
                )
                return True
            if policy and is_in_list(policy.can_manage_access):
                safe_log_info(
                    app_logger,
                    "Manage access permission granted for user %s via policy can_manage_access",
                    user_id_str,
                )
                return True
            safe_log_info(
                app_logger, "Manage access permission denied for user %s", user_id_str
            )
            return False

        # VIEW RESPONSES
        if action == "view_responses":
            if is_in_list(form.editors):
                safe_log_info(
                    app_logger,
                    "View responses permission granted for user %s via editors list",
                    user_id_str,
                )
                return True
            if policy and is_in_list(policy.can_view_responses):
                safe_log_info(
                    app_logger,
                    "View responses permission granted for user %s via policy can_view_responses",
                    user_id_str,
                )
                return True
            safe_log_info(
                app_logger, "View responses permission denied for user %s", user_id_str
            )
            return False

        # EDIT RESPONSES
        if action == "edit_responses":
            if is_in_list(form.editors):
                safe_log_info(
                    app_logger,
                    "Edit responses permission granted for user %s via editors list",
                    user_id_str,
                )
                return True
            if policy and is_in_list(policy.can_edit_responses):
                safe_log_info(
                    app_logger,
                    "Edit responses permission granted for user %s via policy can_edit_responses",
                    user_id_str,
                )
                return True
            safe_log_info(
                app_logger, "Edit responses permission denied for user %s", user_id_str
            )
            return False

        # DELETE RESPONSES
        if action == "delete_responses":
            if "admin" in user_roles:
                safe_log_info(
                    app_logger,
                    "Delete responses permission granted for user %s via admin role",
                    user_id_str,
                )
                return True
            if policy and is_in_list(policy.can_delete_responses):
                safe_log_info(
                    app_logger,
                    "Delete responses permission granted for user %s via policy can_delete_responses",
                    user_id_str,
                )
                return True
            safe_log_info(
                app_logger,
                "Delete responses permission denied for user %s",
                user_id_str,
            )
            return False

        # VIEW AUDIT
        if action == "view_audit":
            if is_in_list(form.editors):
                safe_log_info(
                    app_logger,
                    "View audit permission granted for user %s via editors list",
                    user_id_str,
                )
                return True
            if policy and is_in_list(policy.can_view_audit_logs):
                safe_log_info(
                    app_logger,
                    "View audit permission granted for user %s via policy can_view_audit_logs",
                    user_id_str,
                )
                return True
            safe_log_info(
                app_logger, "View audit permission denied for user %s", user_id_str
            )
            return False

        # DELETE FORM
        if action == "delete_form":
            if "admin" in user_roles:
                safe_log_info(
                    app_logger,
                    "Delete form permission granted for user %s via admin role",
                    user_id_str,
                )
                return True
            if policy and is_in_list(policy.can_delete_form):
                safe_log_info(
                    app_logger,
                    "Delete form permission granted for user %s via policy can_delete_form",
                    user_id_str,
                )
                return True
            safe_log_info(
                app_logger, "Delete form permission denied for user %s", user_id_str
            )
            return False

        app_logger.warning(f"Unknown action '{action}' for form permission check")
        return False

    @staticmethod
    def check_response_permission(
        user: Optional[User],
        response: FormResponse,
        action: Literal["view", "edit", "delete"],
    ) -> bool:
        """
        Check if a user has permission to perform an action on a response.
        """
        if not user or not response:
            return False

        user_id_str = str(user.id)
        user_roles = getattr(user, "roles", []) or []

        # 1. Enforce tenant isolation
        if getattr(user, "organization_id", None) != getattr(
            response, "organization_id", None
        ):
            return False

        # 2. Superadmin always has all permissions
        if "superadmin" in user_roles:
            return True

        # 3. Response owner can view and edit their own responses
        if action in ("view", "edit") and str(response.submitted_by) == user_id_str:
            return True

        # 4. Admin can do anything
        if "admin" in user_roles:
            return True

        # 5. Check form-level permissions
        if hasattr(response, "form") and response.form:
            from models.Form import Form

            try:
                form = Form.objects(id=response.form.id).first()
                if form:
                    if action == "view":
                        return AccessControlService.check_form_permission(
                            user, form, "view_responses"
                        )
                    elif action == "edit":
                        return AccessControlService.check_form_permission(
                            user, form, "edit_responses"
                        )
                    elif action == "delete":
                        return AccessControlService.check_form_permission(
                            user, form, "delete_responses"
                        )
            except Exception:
                pass

        return False

    @staticmethod
    def check_dashboard_permission(
        user: Optional[User],
        dashboard: Dashboard,
        action: Literal["view", "edit", "delete"],
    ) -> bool:
        """
        Check if a user has permission to perform an action on a dashboard.
        """
        if not user or not dashboard:
            return False

        user_id_str = str(user.id)
        user_roles = getattr(user, "roles", []) or []

        # 1. Enforce tenant isolation
        if getattr(user, "organization_id", None) != getattr(
            dashboard, "organization_id", None
        ):
            return False

        # 2. Superadmin always has all permissions
        if "superadmin" in user_roles:
            return True

        # 3. Dashboard owner can do anything
        if str(dashboard.created_by) == user_id_str:
            return True

        # 4. Admin can do anything
        if "admin" in user_roles:
            return True

        # 5. Check dashboard-level ACLs (if exists)
        editors = getattr(dashboard, "editors", [])
        viewers = getattr(dashboard, "viewers", [])

        if action == "view":
            if user_id_str in editors or user_id_str in viewers:
                return True
        elif action in ("edit", "delete"):
            if user_id_str in editors:
                return True

        return False

    @staticmethod
    def check_project_permission(
        user: Optional[User],
        project: Project,
        action: Literal["view", "edit", "delete"],
    ) -> bool:
        """
        Check if a user has permission to perform an action on a project.
        """
        if not user or not project:
            return False

        user_id_str = str(user.id)
        user_roles = getattr(user, "roles", []) or []

        # 1. Enforce tenant isolation
        if getattr(user, "organization_id", None) != getattr(
            project, "organization_id", None
        ):
            return False

        # 2. Superadmin always has all permissions
        if "superadmin" in user_roles:
            return True

        # 3. Project owner can do anything, when the model carries creator metadata
        project_created_by = getattr(project, "created_by", None)
        if project_created_by is not None and str(project_created_by) == user_id_str:
            return True

        # 4. Admin can do anything
        if "admin" in user_roles:
            return True

        # 5. Resource-level ACLs for the project
        try:
            resource_acl = ResourceAccessControl.objects(
                resource_type="project",
                resource_id=str(project.id),
                is_deleted=False,
            ).first()
        except Exception:
            resource_acl = None

        if resource_acl:
            acl_permissions = {"edit", "manage_access", "publish"}

            if action == "view" and resource_acl.access_level in (
                "organization",
                "public",
            ):
                return True

            if (
                action in ("edit", "delete")
                and resource_acl.owner
                and str(resource_acl.owner.id) == user_id_str
            ):
                return True

            if action in ("edit", "delete"):
                for entry in resource_acl.access_list or []:
                    if entry.grantee_type == "user" and entry.grantee_user:
                        if str(
                            entry.grantee_user.id
                        ) == user_id_str and acl_permissions.intersection(
                            set(entry.permissions or [])
                        ):
                            return True
                    if entry.grantee_type == "group" and entry.grantee_group:
                        group = entry.grantee_group
                        if user_id_str in [
                            str(member.id) for member in (group.members or [])
                        ]:
                            if acl_permissions.intersection(
                                set(entry.permissions or [])
                            ):
                                return True

        return False

    @staticmethod
    def apply_row_filtering(queryset, user: User):
        """
        Row-level filtering foundation. Filters documents based on user roles and visibility access.
        """
        user_roles = getattr(user, "roles", []) or []
        if "superadmin" in user_roles or "admin" in user_roles:
            return queryset
        
        # Non-admins: only return documents that are public or created by the user,
        # or where the user is listed in editors/viewers.
        from mongoengine import Q
        return queryset.filter(
            Q(is_public=True) | 
            Q(created_by=str(user.id)) | 
            Q(viewers__in=[str(user.id)]) | 
            Q(editors__in=[str(user.id)])
        )

    @staticmethod
    def apply_field_masking(data: dict, user: User, sensitive_fields: List[str] = None) -> dict:
        """
        Field-level masking foundation. Masks sensitive fields (e.g. email, phone, PII) 
        if the user lacks the permission to view sensitive data.
        """
        if not data:
            return data
        
        user_roles = getattr(user, "roles", []) or []
        
        # If user has the permission to view sensitive data, return unmasked
        if "superadmin" in user_roles or "admin" in user_roles or "manager" in user_roles:
            return data
            
        masked_data = data.copy()
        fields_to_mask = sensitive_fields or ["email", "mobile", "phone", "ssn", "national_id"]
        for field in fields_to_mask:
            if field in masked_data and masked_data[field]:
                val = str(masked_data[field])
                if len(val) > 4:
                    masked_data[field] = val[:2] + "****" + val[-2:]
                else:
                    masked_data[field] = "****"
        return masked_data

