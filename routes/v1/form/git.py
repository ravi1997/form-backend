from . import form_bp
from flasgger import swag_from
import uuid
from flask import request, jsonify, g
from flask_jwt_extended import jwt_required
from mongoengine import DoesNotExist

from logger.unified_logger import app_logger, audit_logger, error_logger
from utils.response_helper import success_response, error_response
from utils.security_helpers import get_current_user, require_permission
from utils.feature_gate import require_feature
from models.form import Form
from models.form_commit import FormCommit
from services.git_form_service import GitFormService
from services.form_service import FormService
from engines.form_engine import FormEngine

git_form_service = GitFormService()
form_engine = FormEngine()
form_service = FormService()


@form_bp.route("/<form_id>/commits", methods=["GET"])
@jwt_required()
@require_feature("git_versioning")
def list_commits(form_id):
    """
    List commit history tree for a specific form.
    """
    try:
        user = get_current_user()
        org_id = user.organization_id

        # Verify form exists and matches org
        form = Form.objects(id=form_id, organization_id=org_id).first()
        if not form:
            return error_response("Form not found", status_code=404)

        commits = form_engine.get_commit_history(form_id, org_id)
        
        return success_response(commits)
    except Exception as e:
        error_logger.error(f"Error listing commits: {e}", exc_info=True)
        return error_response(str(e))


@form_bp.route("/<form_id>/commits", methods=["POST"])
@jwt_required()
@require_feature("git_versioning")
def create_commit(form_id):
    """
    Create a new commit for the form.
    Expects request body: {"message": "commit message", "content": {...}}
    """
    try:
        user = get_current_user()
        org_id = user.organization_id
        data = request.get_json() or {}

        message = data.get("message", "Updated form configuration")
        content = data.get("content", {})
        branch = data.get("branch", "main")

        # Verify form exists and matches org
        form = Form.objects(id=form_id, organization_id=org_id).first()
        if not form:
            return error_response("Form not found", status_code=404)

        # Create commit using form engine
        commit = form_engine.create_commit(
            form_id=form_id,
            organization_id=org_id,
            content=content,
            message=message,
            branch=branch,
            author_id=str(user.id)
        )

        audit_logger.info(
            f"User {user.id} committed form {form_id} with hash {commit.commit_id}"
        )

        return success_response(
            {
                "commit_id": commit.commit_id,
                "message": commit.message,
                "branch": commit.branch,
                "timestamp": commit.timestamp.isoformat(),
                "parent_ids": commit.parent_ids
            },
            message="Commit created successfully",
        )
    except Exception as e:
        error_logger.error(f"Error creating commit: {e}", exc_info=True)
        return error_response(str(e))


@form_bp.route("/<form_id>/branches", methods=["POST"])
@jwt_required()
@require_feature("git_versioning")
def create_branch(form_id):
    """
    Create a new branch for the form.
    Expects request body: {"branch_name": "...", "from_commit_id": "..."}
    """
    try:
        user = get_current_user()
        org_id = user.organization_id
        data = request.get_json() or {}

        branch_name = data.get("branch_name")
        from_commit_id = data.get("from_commit_id")

        if not branch_name:
            return error_response("Branch name is required", status_code=400)

        # Verify form exists and matches org
        form = Form.objects(id=form_id, organization_id=org_id).first()
        if not form:
            return error_response("Form not found", status_code=404)

        # Create branch using form engine
        result = form_engine.create_branch(
            form_id=form_id,
            organization_id=org_id,
            branch_name=branch_name,
            from_commit_id=from_commit_id,
            author_id=str(user.id)
        )

        audit_logger.info(
            f"User {user.id} created branch {branch_name} for form {form_id}"
        )

        return success_response(result, message="Branch created successfully")
    except Exception as e:
        error_logger.error(f"Error creating branch: {e}", exc_info=True)
        return error_response(str(e))


@form_bp.route("/<form_id>/merge", methods=["POST"])
@jwt_required()
@require_feature("git_versioning")
def merge_branches(form_id):
    """
    Merge source branch into target branch.
    Expects request body: {"source_branch": "...", "target_branch": "...", "message": "...", "theirs_commit_id": "...", "mine_commit_id": "...", "resolutions": {...}}
    """
    try:
        user = get_current_user()
        org_id = user.organization_id
        data = request.get_json() or {}

        source_branch = data.get("source_branch")
        target_branch = data.get("target_branch", "main")
        merge_message = data.get("message")
        
        theirs_commit_id = data.get("theirs_commit_id")
        mine_commit_id = data.get("mine_commit_id")
        resolutions = data.get("resolutions")

        if not source_branch and not mine_commit_id:
            return error_response("Source branch or mine_commit_id is required", status_code=400)

        # Verify form exists and matches org
        form = Form.objects(id=form_id, organization_id=org_id).first()
        if not form:
            return error_response("Form not found", status_code=404)

        # Perform merge using form engine
        result = form_engine.merge_branch(
            form_id=form_id,
            organization_id=org_id,
            source_branch=source_branch,
            target_branch=target_branch,
            author_id=str(user.id),
            message=merge_message,
            source_commit_id=mine_commit_id,
            target_commit_id=theirs_commit_id,
            resolutions=resolutions
        )

        audit_logger.info(
            f"User {user.id} merged {source_branch or mine_commit_id} into {target_branch or theirs_commit_id} for form {form_id}"
        )

        return success_response(result, message="Merge status updated")
    except Exception as e:
        error_logger.error(f"Error during merge: {e}", exc_info=True)
        return error_response(str(e))


@form_bp.route("/<form_id>/branches/<branch_name>/set-production", methods=["POST"])
@jwt_required()
@require_feature("git_versioning")
def set_production_branch(form_id, branch_name):
    """
    Set a branch as the production branch.
    """
    try:
        user = get_current_user()
        org_id = user.organization_id

        # Verify form exists and matches org
        form = Form.objects(id=form_id, organization_id=org_id).first()
        if not form:
            return error_response("Form not found", status_code=404)

        # Set production branch using form engine
        result = form_engine.set_production_branch(
            form_id=form_id,
            organization_id=org_id,
            branch_name=branch_name
        )

        audit_logger.info(
            f"User {user.id} set {branch_name} as production branch for form {form_id}"
        )

        return success_response(result, message="Production branch updated successfully")
    except Exception as e:
        error_logger.error(f"Error setting production branch: {e}", exc_info=True)
        return error_response(str(e))


@form_bp.route("/<form_id>/commits/<commit_id>", methods=["GET"])
@jwt_required()
@require_feature("git_versioning")
def get_commit(form_id, commit_id):
    """
    Get form schema at a specific commit.
    """
    try:
        user = get_current_user()
        org_id = user.organization_id

        # Verify form exists and matches org
        form = Form.objects(id=form_id, organization_id=org_id).first()
        if not form:
            return error_response("Form not found", status_code=404)

        # Get form at commit using form engine
        form_schema = form_engine.get_form_at_commit(
            form_id=form_id,
            commit_id=commit_id,
            organization_id=org_id
        )

        return success_response({
            "commit_id": commit_id,
            "form_schema": form_schema
        })
    except Exception as e:
        error_logger.error(f"Error getting commit: {e}", exc_info=True)
        return error_response(str(e))
