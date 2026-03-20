from . import form_bp
from flask_jwt_extended import get_jwt_identity
from models import User


def get_current_user():
    user_id = get_jwt_identity()
    return User.objects(id=user_id).first()


def has_form_permission(user, form, action):
    """
    Check if a user has permission to perform a specific action on a form.
    Supported actions:
    - view: Can view/open the form
    - submit: Can submit responses
    - edit: Can edit form design/questions
    - manage_access: Can manage permissions/access policy
    - view_responses: Can view submission list
    - edit_responses: Can edit existing responses
    - delete_responses: Can delete responses
    - view_audit: Can view form/response history
    - delete_form: Can delete the entire form
    """
    user_id_str = str(user.id)
    user_roles = user.roles or []
    user_dept = getattr(user, "department", None)

    # Enforce tenant isolation before evaluating role or policy permissions.
    if getattr(user, "organization_id", None) != getattr(form, "organization_id", None):
        return False

    # Superadmin always has all permissions
    if hasattr(user, "is_superadmin_check") and user.is_superadmin_check():
        return True

    # Creator always has all permissions
    if str(form.created_by) == user_id_str:
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
            return True
        if policy:
            if policy.form_visibility == "public":
                return True
            if policy.form_visibility == "restricted":
                if user_dept and user_dept in (policy.allowed_departments or []):
                    return True
                if is_in_list(policy.can_view_responses):
                    return True
        return False

    # 2. SUBMIT FORM
    if action == "submit":
        if form.is_public or user_id_str in (form.submitters or []):
            return True
        if policy:
            if policy.form_visibility == "public":
                return True
            if user_dept and user_dept in (policy.allowed_departments or []):
                return True
        return False

    # 3. EDIT DESIGN / CREATE VERSIONS
    if action in ("edit", "edit_design"):
        if user_id_str in (form.editors or []):
            return True
        if policy and is_in_list(policy.can_edit_design):
            return True
        return False

    # 4. MANAGE ACCESS
    if action == "manage_access":
        if hasattr(user, "is_admin_check") and user.is_admin_check():
            return True
        if policy and is_in_list(policy.can_manage_access):
            return True
        return False

    # 5. RESPONSES
    if action == "view_responses":
        if user_id_str in (form.editors or []):
            return True
        if policy and is_in_list(policy.can_view_responses):
            return True
        return False

    if action == "edit_responses":
        if user_id_str in (form.editors or []):
            return True
        if policy and is_in_list(policy.can_edit_responses):
            return True
        return False

    if action == "delete_responses":
        if hasattr(user, "is_admin_check") and user.is_admin_check():
            return True
        if policy and is_in_list(policy.can_delete_responses):
            return True
        return False

    # 6. AUDIT / HISTORY
    if action == "view_audit":
        if user_id_str in (form.editors or []):
            return True
        if policy and is_in_list(policy.can_view_audit_logs):
            return True
        return False

    # 7. DELETE FORM
    if action == "delete_form":
        if hasattr(user, "is_admin_check") and user.is_admin_check():
            return True
        if policy and is_in_list(policy.can_delete_form):
            return True
        return False

    return False


def apply_translations(form_dict, lang_code):
    """
    Applies translations to a form dictionary based on the provided language code.
    If translations for lang_code don't exist, returns the original dict.
    """
    if "versions" not in form_dict or not form_dict["versions"]:
        return form_dict

    latest_version = form_dict["versions"][-1]
    translations = latest_version.get("translations", {})

    if lang_code not in translations:
        return form_dict

    lang_translations = translations[lang_code]

    # Translate Top-level Form title/description
    if "title" in lang_translations:
        form_dict["title"] = lang_translations["title"]
    if "description" in lang_translations:
        form_dict["description"] = lang_translations["description"]

    # Translate Sections
    section_translations = lang_translations.get("sections", {})
    for section in latest_version.get("sections", []):
        sid = str(section.get("id") or section.get("_id"))
        if sid in section_translations:
            if "title" in section_translations[sid]:
                section["title"] = section_translations[sid]["title"]
            if "description" in section_translations[sid]:
                section["description"] = section_translations[sid]["description"]

        # Translate Questions
        question_translations = lang_translations.get("questions", {})
        for question in section.get("questions", []):
            qid = str(question.get("id") or question.get("_id"))
            if qid in question_translations:
                q_trans = question_translations[qid]
                if "label" in q_trans:
                    question["label"] = q_trans["label"]
                if "help_text" in q_trans:
                    question["help_text"] = q_trans["help_text"]
                if "placeholder" in q_trans:
                    question["placeholder"] = q_trans["placeholder"]

                # Translate Options
                if "options" in q_trans and "options" in question:
                    option_translations = q_trans["options"]
                    for option in question.get("options", []):
                        oid = str(option.get("id") or option.get("_id"))
                        if oid in option_translations:
                            option["option_label"] = option_translations[oid]

    return form_dict
