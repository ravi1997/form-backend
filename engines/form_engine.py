"""
engines/form_engine.py
Core form engine providing Git-like versioning, branching, and merge capabilities for forms.
Implements commit, branch, merge, and visibility evaluation functionality.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from mongoengine import Q
from models.form import Form, FormVersion, Section, Question
from models.form_commit import FormCommit, PendingMerge, EditSession
from models.base import BaseDocument
from services.git_form_service import GitFormService
from utils.exceptions import ConflictError, NotFoundError, StateTransitionError
from logger.unified_logger import audit_logger, app_logger

logger = logging.getLogger(__name__)


class FormEngine:
    """
    Core form engine providing Git-like versioning, branching, and merge capabilities.
    Handles form schema versioning, commit management, and 3-way merge resolution.
    """

    def __init__(self):
        self.git_service = GitFormService()

    def _generate_commit_id(self, form_id: str, content: Dict[str, Any]) -> str:
        """
        Generate a SHA-256 commit ID based on form content and timestamp.
        """
        content_str = json.dumps(content, sort_keys=True, default=str)
        timestamp = datetime.now(timezone.utc).isoformat()
        combined = f"{form_id}:{timestamp}:{content_str}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def create_commit(
        self,
        form_id: str,
        organization_id: str,
        content: Dict[str, Any],
        message: str,
        branch: str = "main",
        author_id: str = None,
        parent_ids: List[str] = None
    ) -> FormCommit:
        """
        Create a new commit for the form with the given content.
        
        Args:
            form_id: The form ID
            organization_id: The organization ID
            content: The form schema content
            message: Commit message
            branch: Branch name (default: "main")
            author_id: User ID of the author
            parent_ids: List of parent commit IDs for merge commits
            
        Returns:
            FormCommit: The created commit
            
        Raises:
            NotFoundError: If form not found
            StateTransitionError: If commit creation fails
        """
        try:
            # Verify form exists and belongs to organization
            form = Form.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not form:
                raise NotFoundError(f"Form {form_id} not found in organization {organization_id}")

            # Generate commit ID
            commit_id = self._generate_commit_id(form_id, content)
            
            # Check if commit already exists (prevent duplicates)
            existing_commit = FormCommit.objects(
                form_id=form_id,
                commit_id=commit_id,
                organization_id=organization_id
            ).first()
            
            if existing_commit:
                raise ConflictError(f"Commit {commit_id} already exists")

            # Create the commit
            commit = FormCommit(
                form_id=form_id,
                commit_id=commit_id,
                organization_id=organization_id,
                author_id=author_id or form.created_by,
                message=message,
                branch=branch,
                parent_ids=parent_ids or [],
                timestamp=datetime.now(timezone.utc),
                schema=content
            )
            
            commit.save()
            
            # Update form's branch reference
            if not hasattr(form, 'branches'):
                form.branches = {}
            form.branches[branch] = commit_id
            form.save()
            
            audit_logger.info(
                f"AUDIT: Created commit {commit_id} for form {form_id} on branch {branch}"
            )
            
            return commit
            
        except Exception as e:
            logger.error(f"Failed to create commit for form {form_id}: {str(e)}", exc_info=True)
            raise StateTransitionError(f"Failed to create commit: {str(e)}")

    def create_branch(
        self,
        form_id: str,
        organization_id: str,
        branch_name: str,
        from_commit_id: str = None,
        author_id: str = None
    ) -> Dict[str, Any]:
        """
        Create a new branch from the specified commit or current HEAD.
        
        Args:
            form_id: The form ID
            organization_id: The organization ID
            branch_name: Name of the new branch
            from_commit_id: Source commit ID (defaults to current HEAD)
            author_id: User ID creating the branch
            
        Returns:
            Dict containing branch info and commit details
            
        Raises:
            NotFoundError: If form or source commit not found
            ConflictError: If branch already exists
        """
        try:
            # Verify form exists
            form = Form.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not form:
                raise NotFoundError(f"Form {form_id} not found")

            # Check if branch already exists
            if hasattr(form, 'branches') and branch_name in form.branches:
                raise ConflictError(f"Branch {branch_name} already exists")

            # Get source commit (HEAD if not specified)
            if from_commit_id:
                source_commit = FormCommit.objects(
                    form_id=form_id,
                    commit_id=from_commit_id,
                    organization_id=organization_id
                ).first()
                
                if not source_commit:
                    raise NotFoundError(f"Source commit {from_commit_id} not found")
            else:
                # Use current HEAD (main branch)
                if not hasattr(form, 'branches') or 'main' not in form.branches:
                    # Create initial commit if none exists
                    initial_content = self._extract_form_content(form)
                    initial_commit = self.create_commit(
                        form_id=form_id,
                        organization_id=organization_id,
                        content=initial_content,
                        message="Initial commit",
                        branch="main",
                        author_id=author_id
                    )
                    source_commit = initial_commit
                else:
                    head_commit_id = form.branches['main']
                    source_commit = FormCommit.objects(
                        form_id=form_id,
                        commit_id=head_commit_id,
                        organization_id=organization_id
                    ).first()
                    
                    if not source_commit:
                        raise NotFoundError(f"HEAD commit not found")

            # Create the new branch by pointing to the source commit
            if not hasattr(form, 'branches'):
                form.branches = {}
            form.branches[branch_name] = source_commit.commit_id
            form.save()
            
            audit_logger.info(
                f"AUDIT: Created branch {branch_name} from commit {source_commit.commit_id} for form {form_id}"
            )
            
            return {
                "branch_name": branch_name,
                "commit_id": source_commit.commit_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source_commit": from_commit_id or "HEAD"
            }
            
        except Exception as e:
            logger.error(f"Failed to create branch {branch_name} for form {form_id}: {str(e)}", exc_info=True)
            raise

    def list_branches(
        self,
        form_id: str,
        organization_id: str
    ) -> List[str]:
        """
        List all branches for a form.
        """
        try:
            form = Form.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            if not form:
                raise NotFoundError(f"Form {form_id} not found")
            
            branches = list(getattr(form, 'branches', {}).keys())
            if not branches:
                branches = ["main"]
            if "main" not in branches:
                branches.insert(0, "main")
            return branches
        except Exception as e:
            logger.error(f"Failed to list branches for form {form_id}: {str(e)}", exc_info=True)
            raise

    def delete_branch(
        self,
        form_id: str,
        organization_id: str,
        branch_name: str
    ) -> Dict[str, Any]:
        """
        Delete a branch. Main branch cannot be deleted.
        """
        try:
            if branch_name == "main":
                raise StateTransitionError("Cannot delete the main branch")
                
            form = Form.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            if not form:
                raise NotFoundError(f"Form {form_id} not found")
                
            if not hasattr(form, 'branches') or branch_name not in form.branches:
                raise NotFoundError(f"Branch {branch_name} not found")
                
            del form.branches[branch_name]
            form.save()
            
            audit_logger.info(
                f"AUDIT: Deleted branch {branch_name} for form {form_id}"
            )
            
            return {
                "form_id": form_id,
                "deleted_branch": branch_name,
                "status": "deleted"
            }
        except Exception as e:
            logger.error(f"Failed to delete branch {branch_name} for form {form_id}: {str(e)}", exc_info=True)
            raise


    def merge_branch(
        self,
        form_id: str,
        organization_id: str,
        source_branch: str = None,
        target_branch: str = "main",
        author_id: str = None,
        message: str = None,
        source_commit_id: str = None,
        target_commit_id: str = None,
        resolutions: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        Merge source branch/commit into target branch/commit with 3-way merge conflict resolution.
        
        Args:
            form_id: The form ID
            organization_id: The organization ID
            source_branch: Source branch name
            target_branch: Target branch name (default: "main")
            author_id: User ID performing the merge
            message: Merge commit message
            source_commit_id: Direct source commit ID (optional)
            target_commit_id: Direct target commit ID (optional)
            resolutions: Conflict resolutions map (path -> "mine"|"theirs") (optional)
            
        Returns:
            Dict containing merge result and any conflicts
            
        Raises:
            NotFoundError: If form or branches not found
            StateTransitionError: If merge fails
        """
        try:
            # Verify form exists
            form = Form.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not form:
                raise NotFoundError(f"Form {form_id} not found")

            # Resolve commit IDs
            s_commit_id = source_commit_id
            if not s_commit_id and source_branch:
                if hasattr(form, 'branches') and source_branch in form.branches:
                    s_commit_id = form.branches[source_branch]
                else:
                    s_commit_id = source_branch # fallback

            t_commit_id = target_commit_id
            if not t_commit_id and target_branch:
                if hasattr(form, 'branches') and target_branch in form.branches:
                    t_commit_id = form.branches[target_branch]
                else:
                    t_commit_id = target_branch # fallback

            if not s_commit_id:
                raise NotFoundError("Source commit or branch not found")
            if not t_commit_id:
                raise NotFoundError("Target commit or branch not found")

            # Get commit objects
            source_commit = FormCommit.objects(
                form_id=form_id,
                commit_id=s_commit_id,
                organization_id=organization_id
            ).first()
            
            target_commit = FormCommit.objects(
                form_id=form_id,
                commit_id=t_commit_id,
                organization_id=organization_id
            ).first()
            
            if not source_commit or not target_commit:
                raise NotFoundError("One or more commits not found")

            # Find common ancestor (base commit)
            base_commit = self._find_common_ancestor(source_commit, target_commit)
            
            # Perform 3-way merge
            if base_commit:
                merged_content, conflicts = self.git_service.calculate_3way_merge(
                    base=base_commit.schema,
                    mine=source_commit.schema,
                    theirs=target_commit.schema,
                    resolutions=resolutions
                )
            else:
                # No common ancestor, use target as base
                merged_content, conflicts = self.git_service.calculate_3way_merge(
                    base={},
                    mine=source_commit.schema,
                    theirs=target_commit.schema,
                    resolutions=resolutions
                )

            if conflicts:
                return {
                    "status": "conflict",
                    "conflicts": conflicts,
                    "merged_at": datetime.now(timezone.utc).isoformat()
                }

            # Create merge commit
            merge_message = message or f"Merge {source_branch or s_commit_id[:8]} into {target_branch or t_commit_id[:8]}"
            
            if resolutions:
                merge_message += " (conflicts resolved)"
                
            merge_commit = self.create_commit(
                form_id=form_id,
                organization_id=organization_id,
                content=merged_content,
                message=merge_message,
                branch=target_branch if (target_branch and hasattr(form, 'branches') and target_branch in form.branches) else "main",
                author_id=author_id,
                parent_ids=[s_commit_id, t_commit_id]
            )
            
            # Update target branch to point to merge commit
            if target_branch and hasattr(form, 'branches') and target_branch in form.branches:
                form.branches[target_branch] = merge_commit.commit_id
                form.save()
            
            audit_logger.info(
                f"AUDIT: Merged {source_branch or s_commit_id} into {target_branch or t_commit_id} for form {form_id}, "
                f"commit {merge_commit.commit_id}"
            )
            
            return {
                "merge_commit_id": merge_commit.commit_id,
                "conflicts": [],
                "merged_at": datetime.now(timezone.utc).isoformat(),
                "status": "completed"
            }
            
        except Exception as e:
            logger.error(f"Failed to merge {source_branch or s_commit_id} into {target_branch or t_commit_id} for form {form_id}: {str(e)}", exc_info=True)
            raise StateTransitionError(f"Merge failed: {str(e)}")

    def _find_common_ancestor(self, commit1: FormCommit, commit2: FormCommit) -> Optional[FormCommit]:
        """
        Find the common ancestor of two commits.
        """
        # Simple implementation: check if they share any parent commits
        # In a real implementation, this would traverse the commit graph
        if not commit1.parent_ids or not commit2.parent_ids:
            return None
            
        for parent_id in commit1.parent_ids:
            if parent_id in commit2.parent_ids:
                parent_commit = FormCommit.objects(
                    commit_id=parent_id,
                    form_id=commit1.form_id,
                    organization_id=commit1.organization_id
                ).first()
                return parent_commit
                
        return None

    def _extract_form_content(self, form: Form) -> Dict[str, Any]:
        """
        Extract form content for initial commit creation.
        """
        content = {
            "ui": {
                "theme": getattr(form, 'ui_config', {}),
                "layout": "single_page",
                "primary_color": "#1976d2",
                "font": "Roboto"
            },
            "access": {
                "type": "org",
                "allowed_org_ids": [str(form.organization_id)],
                "allow_anonymous": False
            },
            "settings": {
                "allow_multiple_submissions": getattr(form, 'allow_anonymous', False),
                "allow_draft_save": True,
                "response_edit_policy": "no_edit"
            },
            "sections": []
        }
        
        # Extract sections
        for section in form.sections or []:
            section_data = {
                "id": section.id,
                "name": section.name,
                "title": section.title,
                "description": section.description,
                "order": section.order,
                "questions": []
            }
            
            # Extract questions
            for question in section.questions or []:
                question_data = {
                    "id": question.id,
                    "name": question.name,
                    "label": question.label,
                    "field_type": question.field_type,
                    "required": question.required,
                    "placeholder": question.placeholder,
                    "description": question.description,
                    "order": question.order
                }
                
                # Add options if present
                if question.options:
                    question_data["options"] = [
                        {
                            "value": opt.value,
                            "label": opt.label,
                            "is_default": opt.is_default
                        }
                        for opt in question.options
                    ]
                
                section_data["questions"].append(question_data)
            
            content["sections"].append(section_data)
        
        return content

    def get_commit_history(
        self,
        form_id: str,
        organization_id: str,
        branch: str = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get commit history for a form, optionally filtered by branch.
        
        Args:
            form_id: The form ID
            organization_id: The organization ID
            branch: Branch name filter (optional)
            limit: Maximum number of commits to return
            
        Returns:
            List of commit dictionaries
        """
        try:
            query = FormCommit.objects(
                form_id=form_id,
                organization_id=organization_id
            ).order_by("-timestamp")
            
            if branch:
                query = query.filter(branch=branch)
                
            commits = list(query.limit(limit))
            
            return [
                {
                    "commit_id": commit.commit_id,
                    "message": commit.message,
                    "branch": commit.branch,
                    "author_id": str(commit.author_id),
                    "timestamp": commit.timestamp.isoformat(),
                    "parent_ids": commit.parent_ids
                }
                for commit in commits
            ]
            
        except Exception as e:
            logger.error(f"Failed to get commit history for form {form_id}: {str(e)}", exc_info=True)
            raise

    def get_form_at_commit(
        self,
        form_id: str,
        commit_id: str,
        organization_id: str
    ) -> Dict[str, Any]:
        """
        Reconstruct form schema as it existed at a specific commit.
        
        Args:
            form_id: The form ID
            commit_id: The commit ID
            organization_id: The organization ID
            
        Returns:
            Form schema at the specified commit
            
        Raises:
            NotFoundError: If commit not found
        """
        try:
            return self.git_service.reconstruct_form_at_commit(
                form_id=form_id,
                commit_id=commit_id,
                organization_id=organization_id
            )
            
        except Exception as e:
            logger.error(f"Failed to get form at commit {commit_id}: {str(e)}", exc_info=True)
            raise NotFoundError(f"Commit {commit_id} not found")

    def set_production_branch(
        self,
        form_id: str,
        organization_id: str,
        branch_name: str = "main"
    ) -> Dict[str, Any]:
        """
        Set the production branch for a form.
        
        Args:
            form_id: The form ID
            organization_id: The organization ID
            branch_name: Branch to set as production
            
        Returns:
            Updated form info
            
        Raises:
            NotFoundError: If form or branch not found
        """
        try:
            form = Form.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not form:
                raise NotFoundError(f"Form {form_id} not found")

            if not hasattr(form, 'branches') or branch_name not in form.branches:
                raise NotFoundError(f"Branch {branch_name} not found")

            # Update production branch
            form.production_branch = branch_name
            form.save()
            
            audit_logger.info(
                f"AUDIT: Set production branch to {branch_name} for form {form_id}"
            )
            
            return {
                "form_id": form_id,
                "production_branch": branch_name,
                "production_commit_id": form.branches[branch_name],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to set production branch for form {form_id}: {str(e)}", exc_info=True)
            raise

    def evaluate_form_visibility(
        self,
        form_id: str,
        organization_id: str,
        user_context: Dict[str, Any]
    ) -> bool:
        """
        Evaluate if a form should be visible to the given user context.
        
        Args:
            form_id: The form ID
            organization_id: The organization ID
            user_context: User context containing roles, groups, etc.
            
        Returns:
            True if form is visible, False otherwise
        """
        try:
            # Get the production version of the form
            form = Form.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not form:
                return False

            # Get production commit
            production_branch = getattr(form, 'production_branch', 'main')
            if not hasattr(form, 'branches') or production_branch not in form.branches:
                return False
                
            commit_id = form.branches[production_branch]
            commit = FormCommit.objects(
                form_id=form_id,
                commit_id=commit_id,
                organization_id=organization_id
            ).first()
            
            if not commit:
                return False

            # Evaluate access rules from schema
            access_config = commit.schema.get('access', {})
            access_type = access_config.get('type', 'org')
            
            if access_type == 'public':
                return True
                
            elif access_type == 'org':
                # Check if user belongs to the organization
                user_org_id = user_context.get('organization_id')
                return str(user_org_id) == str(organization_id)
                
            elif access_type == 'groups':
                # Check if user belongs to allowed groups
                allowed_group_ids = access_config.get('allowed_group_ids', [])
                user_group_ids = user_context.get('group_ids', [])
                return any(group_id in allowed_group_ids for group_id in user_group_ids)
                
            elif access_type == 'users':
                # Check if user is in allowed users list
                allowed_user_ids = access_config.get('allowed_user_ids', [])
                user_id = user_context.get('user_id')
                return str(user_id) in allowed_user_ids
                
            return False
            
        except Exception as e:
            logger.error(f"Failed to evaluate form visibility for {form_id}: {str(e)}", exc_info=True)
            return False