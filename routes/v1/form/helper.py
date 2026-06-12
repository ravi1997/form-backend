from . import form_bp
from flask_jwt_extended import get_jwt_identity
from models import User
from logger.unified_logger import app_logger
from utils.sensitive_data_redaction import safe_log_info


def apply_translations(form_dict, lang):
    """Apply a language-specific translation payload to a serialized form dict."""
    if not isinstance(form_dict, dict):
        return form_dict

    translations = form_dict.get("translations") or {}
    lang_payload = translations.get(lang) or {}
    if not lang_payload:
        return form_dict

    translated = dict(form_dict)

    for key in ("title", "description", "help_text"):
        if lang_payload.get(key):
            translated[key] = lang_payload[key]

    sections = translated.get("sections") or []
    section_overrides = lang_payload.get("sections") or {}
    question_overrides = lang_payload.get("questions") or {}

    if sections:
        translated_sections = []
        for section in sections:
            if not isinstance(section, dict):
                translated_sections.append(section)
                continue

            section_id = str(section.get("id", ""))
            updated_section = dict(section)
            section_patch = section_overrides.get(section_id) or {}
            for key in ("title", "description", "help_text"):
                if section_patch.get(key):
                    updated_section[key] = section_patch[key]

            questions = updated_section.get("questions") or []
            if questions:
                updated_questions = []
                for question in questions:
                    if not isinstance(question, dict):
                        updated_questions.append(question)
                        continue

                    question_id = str(question.get("id", ""))
                    question_patch = question_overrides.get(question_id) or {}
                    if question_patch:
                        merged_question = dict(question)
                        for key, value in question_patch.items():
                            if value is not None:
                                merged_question[key] = value
                        updated_questions.append(merged_question)
                    else:
                        updated_questions.append(question)
                updated_section["questions"] = updated_questions

            translated_sections.append(updated_section)

        translated["sections"] = translated_sections

    return translated


def resolve_translation_language(
    translations: dict,
    requested_lang: str = None,
    fallback_lang: str = None,
    default_lang: str = None,
):
    """Select the first available translation language in precedence order."""
    if not isinstance(translations, dict):
        return None

    def _variants(value):
        if not value:
            return []
        text = str(value).strip().replace("_", "-")
        if not text:
            return []
        parts = [part for part in text.split("-") if part]
        if not parts:
            return []
        base = parts[0].lower()
        if len(parts) == 1:
            return [base]
        region = parts[1].upper() if len(parts[1]) == 2 else parts[1].lower()
        tail = [part.lower() for part in parts[2:]]
        normalized = "-".join([base, region, *tail]) if tail else "-".join([base, region])
        variants = [normalized]
        if base not in variants:
            variants.append(base)
        return variants

    candidates = []
    for candidate in (requested_lang, fallback_lang, default_lang):
        for variant in _variants(candidate):
            if variant not in candidates:
                candidates.append(variant)

    for candidate in candidates:
        if translations.get(candidate):
            return candidate
    return None


def get_current_user():
    app_logger.info("Entering get_current_user helper")
    user_id = get_jwt_identity()
    return User.objects(id=user_id).first()


def has_form_permission(user, form, action):
    """Check if a user has permission to perform a specific action on a form."""
    safe_log_info(
        app_logger,
        "Checking permission '%s' for user %s on form %s",
        action,
        str(user.id),
        str(form.id),
    )
    user_id_str = str(user.id)
    user_roles = user.roles or []
    user_dept = getattr(user, "department", None)

    if getattr(user, "organization_id", None) != getattr(form, "organization_id", None):
        safe_log_info(
            app_logger,
            "Tenant mismatch: user org %s != form org %s",
            getattr(user, "organization_id", None),
            getattr(form, "organization_id", None),
        )
        return False

    if hasattr(user, "is_superadmin_check") and user.is_superadmin_check():
        safe_log_info(
            app_logger, "User %s is superadmin, permission granted", str(user.id)
        )
        return True

    if str(form.created_by) == user_id_str:
        safe_log_info(app_logger, "User %s is creator, permission granted", str(user.id))
        return True

    def is_in_list(target_list):
        if not target_list:
            return False
        if user_id_str in target_list:
            return True
        return any(role in target_list for role in user_roles)

    policy = form.access_policy if getattr(form, "access_policy", None) else None

    if action == "view":
        if user_id_str in (form.viewers or []) or user_id_str in (form.editors or []) or form.is_public:
            safe_log_info(
                app_logger,
                "View permission granted for user %s via viewers/editors/public",
                str(user.id),
            )
            return True
        if policy:
            if policy.form_visibility == "public":
                safe_log_info(
                    app_logger,
                    "View permission granted for user %s via public policy",
                    str(user.id),
                )
                return True
            if policy.form_visibility == "restricted":
                if user_dept and user_dept in (policy.allowed_departments or []):
                    safe_log_info(
                        app_logger,
                        "View permission granted for user %s via department %s",
                        str(user.id),
                        user_dept,
                    )
                    return True
                if is_in_list(policy.can_view_responses):
                    safe_log_info(
                        app_logger,
                        "View permission granted for user %s via can_view_responses list",
                        str(user.id),
                    )
                    return True
        safe_log_info(app_logger, "View permission denied for user %s", str(user.id))
        return False

    if action == "submit":
        safe_log_info(app_logger, "Submit permission granted for user %s (org match)", str(user.id))
        return True

    if action in ("edit", "edit_design"):
        if user_id_str in (form.editors or []):
            safe_log_info(
                app_logger,
                "Edit permission granted for user %s via editors list",
                str(user.id),
            )
            return True
        if policy and is_in_list(policy.can_edit_design):
            safe_log_info(
                app_logger,
                "Edit permission granted for user %s via policy can_edit_design",
                str(user.id),
            )
            return True
        safe_log_info(app_logger, "Edit permission denied for user %s", str(user.id))
        return False

    if action == "manage_access":
        if hasattr(user, "is_admin_check") and user.is_admin_check():
            safe_log_info(
                app_logger,
                "Manage access permission granted for user %s via admin check",
                str(user.id),
            )
            return True
        if policy and is_in_list(policy.can_manage_access):
            safe_log_info(
                app_logger,
                "Manage access permission granted for user %s via policy can_manage_access",
                str(user.id),
            )
            return True
        safe_log_info(app_logger, "Manage access permission denied for user %s", str(user.id))
        return False

    if action == "view_responses":
        if user_id_str in (form.editors or []):
            safe_log_info(
                app_logger,
                "View responses permission granted for user %s via editors list",
                str(user.id),
            )
            return True
        if policy and is_in_list(policy.can_view_responses):
            safe_log_info(
                app_logger,
                "View responses permission granted for user %s via policy can_view_responses",
                str(user.id),
            )
            return True
        safe_log_info(app_logger, "View responses permission denied for user %s", str(user.id))
        return False

    if action == "edit_responses":
        if user_id_str in (form.editors or []):
            safe_log_info(
                app_logger,
                "Edit responses permission granted for user %s via editors list",
                str(user.id),
            )
            return True
        if policy and is_in_list(policy.can_edit_responses):
            safe_log_info(
                app_logger,
                "Edit responses permission granted for user %s via policy can_edit_responses",
                str(user.id),
            )
            return True
        safe_log_info(app_logger, "Edit responses permission denied for user %s", str(user.id))
        return False

    if action == "delete_responses":
        if hasattr(user, "is_admin_check") and user.is_admin_check():
            safe_log_info(
                app_logger,
                "Delete responses permission granted for user %s via admin check",
                str(user.id),
            )
            return True
        if policy and is_in_list(policy.can_delete_responses):
            safe_log_info(
                app_logger,
                "Delete responses permission granted for user %s via policy can_delete_responses",
                str(user.id),
            )
            return True
        safe_log_info(app_logger, "Delete responses permission denied for user %s", str(user.id))
        return False

    if action == "view_audit":
        if user_id_str in (form.editors or []):
            safe_log_info(
                app_logger,
                "View audit permission granted for user %s via editors list",
                str(user.id),
            )
            return True
        if policy and is_in_list(policy.can_view_audit_logs):
            safe_log_info(
                app_logger,
                "View audit permission granted for user %s via policy can_view_audit_logs",
                str(user.id),
            )
            return True
        safe_log_info(app_logger, "View audit permission denied for user %s", str(user.id))
        return False

    if action == "delete_form":
        if hasattr(user, "is_admin_check") and user.is_admin_check():
            safe_log_info(
                app_logger,
                "Delete form permission granted for user %s via admin check",
                str(user.id),
            )
            return True
        if policy and is_in_list(policy.can_delete_form):
            safe_log_info(
                app_logger,
                "Delete form permission granted for user %s via policy can_delete_form",
                str(user.id),
            )
            return True
        safe_log_info(app_logger, "Delete form permission denied for user %s", str(user.id))
        return False

    app_logger.warning(f"Unknown action '{action}' for permission check")
    return False
