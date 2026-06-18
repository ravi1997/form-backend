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
from models.form import FormVersion as FormCommit
from services.git_form_service import GitFormService

git_form_service = GitFormService()


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

        commits = GitFormService.get_commit_history(form_id, org_id)
        commits_data = [commit.to_dict() for commit in commits]

        return success_response(commits_data)
    except Exception as e:
        error_logger.error(f"Error listing commits: {e}", exc_info=True)
        return error_response(str(e))


@form_bp.route("/<form_id>/commits", methods=["POST"])
@jwt_required()
@require_feature("git_versioning")
def create_commit(form_id):
    """
    Create a new snapshot commit of the form configuration (saving a draft).
    Expects request body: {"message": "commit message", "form_data": {...}}
    """
    try:
        user = get_current_user()
        org_id = user.organization_id
        data = request.get_json() or {}

        message = data.get("message", "Updated form configuration")
        form_data = data.get("form_data", {})

        form = Form.objects(id=form_id, organization_id=org_id).first()
        if not form:
            return error_response("Form not found", status_code=404)

        # 1. Reconstruct current HEAD configuration to calculate patch
        head_data = {}
        if form.head_commit_id:
            head_data = GitFormService.reconstruct_form_at_commit(
                form_id, str(form.head_commit_id), org_id
            )

        # 2. Generate RFC 6902 patch operations from HEAD to new form_data
        patch_ops = GitFormService.diff(head_data, form_data)

        # 3. Create the FormCommit document
        new_commit = FormCommit(
            form_id=uuid.UUID(form_id),
            parent_commit_id=form.head_commit_id,
            author_id=str(user.id),
            message=message,
            patch=patch_ops,
            organization_id=org_id,
        )
        new_commit.save()

        # 4. Advance Form local HEAD pointer to the new commit
        form.head_commit_id = new_commit.id
        form.save()

        # Audit log creation
        audit_logger.info(
            f"User {user.id} committed form {form_id} changes with hash {new_commit.id} (patch len: {len(patch_ops)})"
        )

        return success_response(
            {"commit_id": str(new_commit.id), "patch_size": len(patch_ops)},
            message="Commit created successfully",
        )
    except Exception as e:
        error_logger.error(f"Error creating commit: {e}", exc_info=True)
        return error_response(str(e))


@form_bp.route("/<form_id>/merge", methods=["POST"])
@jwt_required()
@require_feature("git_versioning")
def merge_branches(form_id):
    """
    Performs 3-way merge conflict check and publishes.
    Expects request body: {"theirs_commit_id": "...", "mine_commit_id": "..."}
    """
    try:
        user = get_current_user()
        org_id = user.organization_id
        data = request.get_json() or {}

        theirs_id = data.get("theirs_commit_id")  # Server main head
        mine_id = data.get("mine_commit_id")  # My local/offline workspace head

        form = Form.objects(id=form_id, organization_id=org_id).first()
        if not form:
            return error_response("Form not found", status_code=404)

        if not theirs_id or not mine_id:
            return error_response(
                "Missing theirs_commit_id or mine_commit_id parameters", status_code=400
            )

        # Find Common Ancestor (simplifying: get parent of mine/theirs, or last shared base)
        # For simplicity and robust correctness, we trace backward to find the first shared UUID
        mine_chain = []
        curr = mine_id
        while curr:
            c = FormCommit.objects(id=curr, organization_id=org_id).first()
            if not c:
                break
            mine_chain.append(str(c.id))
            curr = c.parent_commit_id

        ancestor_id = None
        curr = theirs_id
        while curr:
            if str(curr) in mine_chain:
                ancestor_id = str(curr)
                break
            c = FormCommit.objects(id=curr, organization_id=org_id).first()
            if not c:
                break
            curr = c.parent_commit_id

        # Reconstruct base, mine, theirs documents
        base_doc = (
            GitFormService.reconstruct_form_at_commit(form_id, ancestor_id, org_id)
            if ancestor_id
            else {}
        )
        mine_doc = GitFormService.reconstruct_form_at_commit(form_id, mine_id, org_id)
        theirs_doc = GitFormService.reconstruct_form_at_commit(
            form_id, theirs_id, org_id
        )

        # Perform 3-Way Merge
        merged_result, conflicts = GitFormService.calculate_3way_merge(
            base_doc, mine_doc, theirs_doc
        )

        if len(conflicts) > 0:
            return success_response(
                {"status": "conflict", "conflicts": conflicts},
                message="Conflicts detected during merge",
            )

        # If no conflicts, create the merged commit automatically!
        patch_ops = GitFormService.diff(theirs_doc, merged_result)
        new_commit = FormCommit(
            form_id=uuid.UUID(form_id),
            parent_commit_id=uuid.UUID(theirs_id),
            author_id=str(user.id),
            message="Auto-merged branches",
            patch=patch_ops,
            organization_id=org_id,
        )
        new_commit.save()

        # Update Head pointer to point to the new merge commit
        form.head_commit_id = new_commit.id
        form.save()

        return success_response(
            {
                "status": "success",
                "merged_commit_id": str(new_commit.id),
                "merged_data": merged_result,
            },
            message="Branches successfully merged with no conflicts!",
        )
    except Exception as e:
        error_logger.error(f"Error during merge: {e}", exc_info=True)
        return error_response(str(e))
