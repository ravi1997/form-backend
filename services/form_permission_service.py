"""
services/form_permission_service.py
Service for managing form permissions and access control.
"""

from typing import Dict, Any, List, Optional, Set
from mongoengine import Q
from logger.unified_logger import (
    app_logger,
    error_logger,
    audit_logger,
    get_logger,
)
from services.base import BaseService
from utils.exceptions import NotFoundError, ValidationError, PermissionError
from models.form import Form, FormCommit
from models.auth import User
from models.identity import Organisation, OrgMembership
from models.identity import Group, GroupMember

logger = get_logger(__name__)


class FormPermissionService(BaseService):
    """
    Service for managing form permissions and access control.
    """

    def __init__(self):
        super().__init__(model=Form, schema=None)  # No schema needed for permission service

    def check_form_access(
        self,
        form_id: str,
        organization_id: str,
        user_context: Dict[str, Any],
        required_permission: str = 'read'
    ) -> bool:
        """
        Check if user has access to a form with the specified permission.
        
        Args:
            form_id: The form ID
            organization_id: The organization ID
            user_context: User context containing user_id, roles, etc.
            required_permission: Permission level required ('read', 'write', 'admin')
            
        Returns:
            True if user has access, False otherwise
        """
        try:
            # Get form
            form = Form.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not form:
                return False
            
            # Get production commit for access rules
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
            
            # Get access configuration
            access_config = commit.schema.get('access', {})
            access_type = access_config.get('type', 'org')
            
            # Check access type
            if access_type == 'public':
                return self._check_public_access(form, user_context, required_permission)
            elif access_type == 'org':
                return self._check_org_access(form, user_context, required_permission)
            elif access_type == 'groups':
                return self._check_group_access(form, access_config, user_context, required_permission)
            elif access_type == 'users':
                return self._check_user_access(form, access_config, user_context, required_permission)
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check form access: {str(e)}", exc_info=True)
            return False

    def _check_public_access(
        self,
        form: Form,
        user_context: Dict[str, Any],
        required_permission: str
    ) -> bool:
        """
        Check access for public forms.
        """
        # Public forms are readable by anyone
        if required_permission == 'read':
            return True
        
        # Write and admin permissions require authentication
        user_id = user_context.get('user_id')
        if not user_id:
            return False
        
        # Check if user is form owner or has admin role
        if str(form.created_by.id) == user_id:
            return True
        
        # Check organization membership for write permissions
        org_membership = OrgMembership.objects(
            user_id=user_id,
            org_id=form.organization_id,
            status='active'
        ).first()
        
        if org_membership:
            if required_permission == 'write' and org_membership.role in ['org_admin', 'org_editor']:
                return True
            elif required_permission == 'admin' and org_membership.role == 'org_admin':
                return True
        
        return False

    def _check_org_access(
        self,
        form: Form,
        user_context: Dict[str, Any],
        required_permission: str
    ) -> bool:
        """
        Check access for organization-restricted forms.
        """
        user_id = user_context.get('user_id')
        if not user_id:
            return False
        
        # Check if user belongs to the organization
        org_membership = OrgMembership.objects(
            user_id=user_id,
            org_id=form.organization_id,
            status='active'
        ).first()
        
        if not org_membership:
            return False
        
        # Check permission level
        if required_permission == 'read':
            return True
        elif required_permission == 'write':
            return org_membership.role in ['org_admin', 'org_editor']
        elif required_permission == 'admin':
            return org_membership.role == 'org_admin'
        
        return False

    def _check_group_access(
        self,
        form: Form,
        access_config: Dict[str, Any],
        user_context: Dict[str, Any],
        required_permission: str
    ) -> bool:
        """
        Check access for group-restricted forms.
        """
        user_id = user_context.get('user_id')
        if not user_id:
            return False
        
        # Get allowed group IDs
        allowed_group_ids = access_config.get('allowed_group_ids', [])
        if not allowed_group_ids:
            return False
        
        # Check if user belongs to any allowed group
        user_groups = GroupMember.objects(
            user_id=user_id,
            group_id__in=allowed_group_ids
        )
        
        if not user_groups:
            return False
        
        # For read access, belonging to any allowed group is sufficient
        if required_permission == 'read':
            return True
        
        # For write and admin permissions, check user's role in the organization
        org_membership = OrgMembership.objects(
            user_id=user_id,
            org_id=form.organization_id,
            status='active'
        ).first()
        
        if not org_membership:
            return False
        
        if required_permission == 'write':
            return org_membership.role in ['org_admin', 'org_editor']
        elif required_permission == 'admin':
            return org_membership.role == 'org_admin'
        
        return False

    def _check_user_access(
        self,
        form: Form,
        access_config: Dict[str, Any],
        user_context: Dict[str, Any],
        required_permission: str
    ) -> bool:
        """
        Check access for user-restricted forms.
        """
        user_id = user_context.get('user_id')
        if not user_id:
            return False
        
        # Get allowed user IDs
        allowed_user_ids = access_config.get('allowed_user_ids', [])
        if str(user_id) not in allowed_user_ids:
            return False
        
        # For read access, being in the allowed list is sufficient
        if required_permission == 'read':
            return True
        
        # For write and admin permissions, check user's role in the organization
        org_membership = OrgMembership.objects(
            user_id=user_id,
            org_id=form.organization_id,
            status='active'
        ).first()
        
        if not org_membership:
            return False
        
        if required_permission == 'write':
            return org_membership.role in ['org_admin', 'org_editor']
        elif required_permission == 'admin':
            return org_membership.role == 'org_admin'
        
        return False

    def get_user_forms(
        self,
        user_id: str,
        organization_id: str = None,
        permission: str = 'read',
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get list of forms accessible to the user.
        
        Args:
            user_id: The user ID
            organization_id: Filter by organization (optional)
            permission: Required permission level
            limit: Maximum number of forms to return
            offset: Offset for pagination
            
        Returns:
            List of accessible forms
        """
        try:
            user_context = {'user_id': user_id}
            
            # Get user's organizations
            org_memberships = OrgMembership.objects(
                user_id=user_id,
                status='active'
            )
            
            org_ids = [str(membership.org_id) for membership in org_memberships]
            
            # Get user's groups
            user_groups = GroupMember.objects(user_id=user_id)
            group_ids = [str(member.group_id) for member in user_groups]
            
            # Build query for forms
            forms_query = Form.objects(is_deleted=False)
            
            if organization_id:
                forms_query = forms_query.filter(organization_id=organization_id)
            else:
                forms_query = forms_query.filter(organization_id__in=org_ids)
            
            accessible_forms = []
            
            for form in forms_query:
                if self.check_form_access(str(form.id), form.organization_id, user_context, permission):
                    accessible_forms.append({
                        'form_id': str(form.id),
                        'name': form.name,
                        'description': form.description,
                        'status': form.status,
                        'organization_id': form.organization_id,
                        'created_at': form.created_at.isoformat(),
                        'updated_at': form.updated_at.isoformat()
                    })
            
            # Apply pagination
            return accessible_forms[offset:offset + limit]
            
        except Exception as e:
            logger.error(f"Failed to get user forms: {str(e)}", exc_info=True)
            raise

    def grant_form_access(
        self,
        form_id: str,
        organization_id: str,
        access_config: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update form access configuration.
        
        Args:
            form_id: The form ID
            organization_id: The organization ID
            access_config: New access configuration
            user_context: User making the change
            
        Returns:
            Updated form information
        """
        try:
            # Check if user has admin permission
            if not self.check_form_access(form_id, organization_id, user_context, 'admin'):
                raise PermissionError("You do not have permission to modify form access")
            
            # Get form and production commit
            form = Form.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not form:
                raise NotFoundError("Form not found")
            
            production_branch = getattr(form, 'production_branch', 'main')
            if not hasattr(form, 'branches') or production_branch not in form.branches:
                raise ValidationError("Form has no production version")
                
            commit_id = form.branches[production_branch]
            commit = FormCommit.objects(
                form_id=form_id,
                commit_id=commit_id,
                organization_id=organization_id
            ).first()
            
            if not commit:
                raise ValidationError("Form production version not found")
            
            # Validate access configuration
            access_type = access_config.get('type')
            if access_type not in ['public', 'org', 'groups', 'users']:
                raise ValidationError("Invalid access type")
            
            if access_type == 'groups':
                allowed_groups = access_config.get('allowed_group_ids', [])
                if not allowed_groups:
                    raise ValidationError("Group access requires at least one group")
                
                # Verify groups exist and belong to the organization
                valid_groups = Group.objects(
                    id__in=allowed_groups,
                    organization_id=organization_id,
                    is_deleted=False
                ).count()
                
                if valid_groups != len(allowed_groups):
                    raise ValidationError("One or more groups not found or not in organization")
            
            elif access_type == 'users':
                allowed_users = access_config.get('allowed_user_ids', [])
                if not allowed_users:
                    raise ValidationError("User access requires at least one user")
                
                # Verify users exist and belong to the organization
                valid_users = OrgMembership.objects(
                    user_id__in=allowed_users,
                    org_id=organization_id,
                    status='active'
                ).count()
                
                if valid_users != len(allowed_users):
                    raise ValidationError("One or more users not found or not in organization")
            
            # Create new commit with updated access configuration
            from engines.form_engine import FormEngine
            
            form_engine = FormEngine()
            new_schema = commit.schema.copy()
            new_schema['access'] = access_config
            
            new_commit = form_engine.create_commit(
                form_id=form_id,
                organization_id=organization_id,
                content=new_schema,
                message=f"Update form access to {access_type}",
                branch=production_branch,
                author_id=user_context.get('user_id')
            )
            
            # Update form branch
            form.branches[production_branch] = new_commit.commit_id
            form.save()
            
            audit_logger.info(
                f"AUDIT: Form access updated for form {form_id} to {access_type} "
                f"by {user_context.get('user_id')}"
            )
            
            return {
                'form_id': form_id,
                'access_type': access_type,
                'commit_id': new_commit.commit_id,
                'updated_at': new_commit.timestamp.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to grant form access: {str(e)}", exc_info=True)
            raise

    def get_form_permissions(
        self,
        form_id: str,
        organization_id: str,
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get user's permissions for a specific form.
        
        Args:
            form_id: The form ID
            organization_id: The organization ID
            user_context: User context
            
        Returns:
            Dictionary of permissions for the form
        """
        try:
            permissions = {
                'can_read': False,
                'can_write': False,
                'can_admin': False,
                'access_type': None,
                'access_details': {}
            }
            
            # Get form and production commit
            form = Form.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not form:
                return permissions
            
            production_branch = getattr(form, 'production_branch', 'main')
            if not hasattr(form, 'branches') or production_branch not in form.branches:
                return permissions
                
            commit_id = form.branches[production_branch]
            commit = FormCommit.objects(
                form_id=form_id,
                commit_id=commit_id,
                organization_id=organization_id
            ).first()
            
            if not commit:
                return permissions
            
            # Get access configuration
            access_config = commit.schema.get('access', {})
            access_type = access_config.get('type', 'org')
            
            permissions['access_type'] = access_type
            permissions['access_details'] = access_config
            
            # Check each permission level
            permissions['can_read'] = self.check_form_access(form_id, organization_id, user_context, 'read')
            permissions['can_write'] = self.check_form_access(form_id, organization_id, user_context, 'write')
            permissions['can_admin'] = self.check_form_access(form_id, organization_id, user_context, 'admin')
            
            return permissions
            
        except Exception as e:
            logger.error(f"Failed to get form permissions: {str(e)}", exc_info=True)
            return {
                'can_read': False,
                'can_write': False,
                'can_admin': False,
                'access_type': None,
                'access_details': {},
                'error': str(e)
            }

    def bulk_check_form_access(
        self,
        form_ids: List[str],
        organization_id: str,
        user_context: Dict[str, Any],
        required_permission: str = 'read'
    ) -> Dict[str, bool]:
        """
        Check access for multiple forms at once.
        
        Args:
            form_ids: List of form IDs to check
            organization_id: The organization ID
            user_context: User context
            required_permission: Required permission level
            
        Returns:
            Dictionary mapping form IDs to access status
        """
        results = {}
        
        for form_id in form_ids:
            try:
                results[form_id] = self.check_form_access(
                    form_id, 
                    organization_id, 
                    user_context, 
                    required_permission
                )
            except Exception as e:
                logger.error(f"Failed to check access for form {form_id}: {str(e)}")
                results[form_id] = False
        
        return results