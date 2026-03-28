from . import form_bp
from flask_jwt_extended import get_jwt_identity
from models import User
from logger.unified_logger import app_logger, error_logger


def get_current_user():
    app_logger.info("Entering get_current_user helper")
    user_id = get_jwt_identity()
    return User.objects(id=user_id).first()


def has_form_permission(user, form, action):
    """
    Check if a user has permission to perform a specific action on a form.
    """
    app_logger.info(f"Checking permission '{action}' for user {user.id} on form {form.id}")
    user_id_str = str(user.id)
    user_roles = user.roles or []
    user_dept = getattr(user, "department", None)

    # Enforce tenant isolation before evaluating role or policy permissions.
    if getattr(user, "organization_id", None) != getattr(form, "organization_id", None):
        app_logger.warning(f"Tenant mismatch: user org {getattr(user, 'organization_id', None)} != form org {getattr(form, 'organization_id', None)}")
        return False

    # Superadmin always has all permissions
    if hasattr(user, "is_superadmin_check") and user.is_superadmin_check():
        app_logger.info(f"User {user.id} is superadmin, permission granted")
        return True

    # Creator always has all permissions
    if str(form.created_by) == user_id_str:
        app_logger.info(f"User {user.id} is creator, permission granted")
        return True

    # Helper to check if user or their roles are in a list
    def is_in_list(target_list):
        if not target_list:
            return False
        if user_id_str in target_list:
            return True
        for role in user_roles:
            if role in target_list:
                return True
        return False

    policy = (
        form.access_policy
        if hasattr(form, "access_policy") and form.access_policy
        else None
    )

    # 1. VIEW FORM
    if action == "view":
        if (
            user_id_str in (form.viewers or [])
            or user_id_str in (form.editors or [])
            or form.is_public
        ):
            app_logger.info(f"View permission granted for user {user.id} via viewers/editors/public")
            return True
        if policy:
            if policy.form_visibility == "public":
                app_logger.info(f"View permission granted for user {user.id} via public policy")
                return True
            if policy.form_visibility == "restricted":
                if user_dept and user_dept in (policy.allowed_departments or []):
                    app_logger.info(f"View permission granted for user {user.id} via department {user_dept}")
                    return True
                if is_in_list(policy.can_view_responses):
                    app_logger.info(f"View permission granted for user {user.id} via can_view_responses list")
                    return True
        app_logger.info(f"View permission denied for user {user.id}")
        return False

    # 2. SUBMIT FORM
    if action == "submit":
        # Allow anyone in the same organization to submit by default
        app_logger.info(f"Submit permission granted for user {user.id} (org match)")
        return True

    # 3. EDIT DESIGN / CREATE VERSIONS
    if action in ("edit", "edit_design"):
        if user_id_str in (form.editors or []):
            app_logger.info(f"Edit permission granted for user {user.id} via editors list")
            return True
        if policy and is_in_list(policy.can_edit_design):
            app_logger.info(f"Edit permission granted for user {user.id} via policy can_edit_design")
            return True
        app_logger.info(f"Edit permission denied for user {user.id}")
        return False

    # 4. MANAGE ACCESS
    if action == "manage_access":
        if hasattr(user, "is_admin_check") and user.is_admin_check():
            app_logger.info(f"Manage access permission granted for user {user.id} via admin check")
            return True
        if policy and is_in_list(policy.can_manage_access):
            app_logger.info(f"Manage access permission granted for user {user.id} via policy can_manage_access")
            return True
        app_logger.info(f"Manage access permission denied for user {user.id}")
        return False

    # 5. RESPONSES
    if action == "view_responses":
        if user_id_str in (form.editors or []):
            app_logger.info(f"View responses permission granted for user {user.id} via editors list")
            return True
        if policy and is_in_list(policy.can_view_responses):
            app_logger.info(f"View responses permission granted for user {user.id} via policy can_view_responses")
            return True
        app_logger.info(f"View responses permission denied for user {user.id}")
        return False

    if action == "edit_responses":
        if user_id_str in (form.editors or []):
            app_logger.info(f"Edit responses permission granted for user {user.id} via editors list")
            return True
        if policy and is_in_list(policy.can_edit_responses):
            app_logger.info(f"Edit responses permission granted for user {user.id} via policy can_edit_responses")
            return True
        app_logger.info(f"Edit responses permission denied for user {user.id}")
        return False

    if action == "delete_responses":
        if hasattr(user, "is_admin_check") and user.is_admin_check():
            app_logger.info(f"Delete responses permission granted for user {user.id} via admin check")
            return True
        if policy and is_in_list(policy.can_delete_responses):
            app_logger.info(f"Delete responses permission granted for user {user.id} via policy can_delete_responses")
            return True
        app_logger.info(f"Delete responses permission denied for user {user.id}")
        return False

    # 6. AUDIT / HISTORY
    if action == "view_audit":
        if user_id_str in (form.editors or []):
            app_logger.info(f"View audit permission granted for user {user.id} via editors list")
            return True
        if policy and is_in_list(policy.can_view_audit_logs):
            app_logger.info(f"View audit permission granted for user {user.id} via policy can_view_audit_logs")
            return True
        app_logger.info(f"View audit permission denied for user {user.id}")
        return False

    # 7. DELETE FORM
    if action == "delete_form":
        if hasattr(user, "is_admin_check") and user.is_admin_check():
            app_logger.info(f"Delete form permission granted for user {user.id} via admin check")
            return True
        if policy and is_in_list(policy.can_delete_form):
            app_logger.info(f"Delete form permission granted for user {user.id} via policy can_delete_form")
            return True
        app_logger.info(f"Delete form permission denied for user {user.id}")
        return False

    app_logger.warning(f"Unknown action '{action}' for permission check")
    return False


def apply_translations(form_dict, lang_code):
    """
    Applies translations to a form dictionary based on the provided language code.
    Checks draft form translations and published version translations.
    """
    app_logger.info(f"Applying translations for lang '{lang_code}'")
    
    # 1. Start with draft translations
    translations = form_dict.get("translations", {})
    
    # 2. Overwrite with version-specific translations if versions exist
    if "versions" in form_dict and form_dict["versions"]:
        # Handle list of FormVersion docs
        latest_version = form_dict["versions"][-1]
        
        # Check snapshot translations first
        snapshot = latest_version.get("snapshot", {})
        if snapshot and "translations" in snapshot:
            translations = snapshot["translations"]
        elif "translations" in latest_version:
            translations = latest_version["translations"]

    if not translations or lang_code not in translations:
        return form_dict

    lang_translations = translations[lang_code]

    # Translate Top-level Form title/description
    if "title" in lang_translations:
        form_dict["title"] = lang_translations["title"]
    if "description" in lang_translations:
        form_dict["description"] = lang_translations["description"]

    # Translate Sections and Questions recursively
    def translate_sections(sections):
        section_translations = lang_translations.get("sections", {})
        question_translations = lang_translations.get("questions", {})
        
        for section in sections:
            sid = str(section.get("id") or section.get("_id"))
            # Support both UUID and title/slug if needed
            if sid in section_translations:
                s_trans = section_translations[sid]
                if "title" in s_trans: section["title"] = s_trans["title"]
                if "description" in s_trans: section["description"] = s_trans["description"]

            # Translate Questions
            for question in section.get("questions", []):
                qid = str(question.get("id") or question.get("_id"))
                var_name = question.get("variable_name")
                
                # Try variable_name first, then qid
                q_trans = question_translations.get(var_name) or question_translations.get(qid)
                
                if q_trans:
                    if "label" in q_trans: question["label"] = q_trans["label"]
                    if "help_text" in q_trans: question["help_text"] = q_trans["help_text"]
                    if "placeholder" in q_trans: 
                        if "ui" not in question: question["ui"] = {}
                        question["ui"]["placeholder"] = q_trans["placeholder"]

                    # Translate Options
                    if "options" in q_trans and "options" in question:
                        option_translations = q_trans["options"]
                        for option in question.get("options", []):
                            # Try option_value as key first, then oid
                            ov = str(option.get("option_value"))
                            oid = str(option.get("id") or option.get("_id"))
                            o_trans = option_translations.get(ov) or option_translations.get(oid)
                            if o_trans:
                                option["option_label"] = o_trans

            # Recurse
            if section.get("sections"):
                translate_sections(section["sections"])

    # Resolve sections list
    sections = []
    if "versions" in form_dict and form_dict["versions"]:
        latest_version = form_dict["versions"][-1]
        snapshot = latest_version.get("snapshot", {})
        if snapshot and "sections" in snapshot:
            sections = snapshot["sections"]
        else:
            sections = latest_version.get("sections", [])
    else:
        sections = form_dict.get("sections", [])
        
    translate_sections(sections)
    return form_dict
