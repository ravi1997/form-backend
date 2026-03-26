from mongoengine.errors import DoesNotExist
from logger.unified_logger import app_logger, error_logger, audit_logger
from services.base import BaseService
from utils.exceptions import NotFoundError
from models import UserGroup, ResourceAccessControl, ApprovalWorkflow, User
from schemas.access_control import (
    UserGroupSchema,
    ResourceAccessControlSchema,
    ApprovalWorkflowSchema,
)
from schemas.base import InboundPayloadSchema


class UserGroupCreateSchema(UserGroupSchema, InboundPayloadSchema):
    pass


class UserGroupUpdateSchema(UserGroupSchema, InboundPayloadSchema):
    pass


class UserGroupService(BaseService):
    def __init__(self):
        super().__init__(model=UserGroup, schema=UserGroupSchema)

    def add_member(self, group_id: str, user_id: str) -> UserGroupSchema:
        """Atomically adds a user to a group if they aren't already a member."""
        app_logger.info(f"Adding member {user_id} to group {group_id}")
        try:
            group = self.model.objects(id=group_id, is_active=True).first()
            if not group:
                app_logger.warning(f"Group {group_id} not found or inactive")
                raise NotFoundError("Group not found or inactive")

            user = User.objects(id=user_id, is_deleted=False).first()
            if not user:
                app_logger.warning(f"User {user_id} not found")
                raise NotFoundError("User not found")

            group.update(add_to_set__members=user)
            group.reload()
            audit_logger.info(f"Added user {user_id} to group {group_id}")
            app_logger.info(f"Successfully added member {user_id} to group {group_id}")
            return self._to_schema(group)
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(f"Failed to add member {user_id} to group {group_id}: {str(e)}", exc_info=True)
            raise

    def remove_member(self, group_id: str, user_id: str) -> UserGroupSchema:
        """Atomically removes a user from a group."""
        app_logger.info(f"Removing member {user_id} from group {group_id}")
        try:
            group = self.model.objects(id=group_id).first()
            if not group:
                app_logger.warning(f"Group {group_id} not found")
                raise NotFoundError("Group not found")

            group.update(pull__members=user_id)
            group.reload()
            audit_logger.info(f"Removed user {user_id} from group {group_id}")
            app_logger.info(f"Successfully removed member {user_id} from group {group_id}")
            return self._to_schema(group)
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(f"Failed to remove member {user_id} from group {group_id}: {str(e)}", exc_info=True)
            raise


class ResourceAccessControlCreateSchema(
    ResourceAccessControlSchema, InboundPayloadSchema
):
    pass


class ResourceAccessControlUpdateSchema(
    ResourceAccessControlSchema, InboundPayloadSchema
):
    pass


class ResourceAccessControlService(BaseService):
    def __init__(self):
        super().__init__(
            model=ResourceAccessControl, schema=ResourceAccessControlSchema
        )

    def get_by_resource(
        self, resource_type: str, resource_id: str
    ) -> ResourceAccessControlSchema:
        """Retrieves ACL policy for a specific resource, ensuring strict environment isolation."""
        app_logger.info(f"Retrieving ACL for {resource_type}:{resource_id}")
        try:
            doc = self.model.objects(
                resource_type=resource_type, resource_id=resource_id, is_active=True
            ).first()

            if not doc:
                app_logger.debug(f"ACL not found for {resource_type}:{resource_id}")
                raise NotFoundError(f"Access policy for this {resource_type} not found")
            
            app_logger.info(f"Successfully retrieved ACL for {resource_type}:{resource_id}")
            return self._to_schema(doc)
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(f"Error retrieving ACL for {resource_type}:{resource_id}: {str(e)}", exc_info=True)
            raise

    def check_permission(
        self, resource_type: str, resource_id: str, user_id: str, permission: str
    ) -> bool:
        """
        Policy Decision Point (PDP): Evaluates if a user has a specific permission on a resource
        considering both direct user grants and inherited group permissions.
        """
        app_logger.info(f"Checking permission '{permission}' for user {user_id} on {resource_type}:{resource_id}")
        try:
            # 1. Get the ACL for the resource
            try:
                acl = self.model.objects.get(
                    resource_type=resource_type, resource_id=resource_id, is_active=True
                )
            except DoesNotExist:
                app_logger.debug(f"No active ACL found for {resource_type}:{resource_id}")
                return False

            # 2. Check public access
            if acl.access_level == "public" and permission == "view":
                app_logger.info(f"Public view access granted for {resource_type}:{resource_id}")
                return True

            # 3. Check for direct user grant
            for entry in acl.entries:
                if entry.grantee_type == "user" and str(entry.grantee_user.id) == user_id:
                    if permission in entry.permissions:
                        app_logger.info(f"Direct permission '{permission}' granted to user {user_id} on {resource_type}:{resource_id}")
                        return True

                # 4. Check for group-based grant
                if entry.grantee_type == "group":
                    group = entry.grantee_group
                    if group.is_active and any(
                        str(member.id) == user_id for member in group.members
                    ):
                        if permission in entry.permissions:
                            app_logger.info(f"Group-based permission '{permission}' granted to user {user_id} via group {group.id} on {resource_type}:{resource_id}")
                            return True

            app_logger.info(f"Permission '{permission}' denied for user {user_id} on {resource_type}:{resource_id}")
            return False
        except Exception as e:
            error_logger.error(f"Error checking permission for user {user_id} on {resource_type}:{resource_id}: {str(e)}", exc_info=True)
            return False


class ApprovalWorkflowCreateSchema(ApprovalWorkflowSchema, InboundPayloadSchema):
    pass


class ApprovalWorkflowUpdateSchema(ApprovalWorkflowSchema, InboundPayloadSchema):
    pass


class ApprovalWorkflowService(BaseService):
    def __init__(self):
        super().__init__(model=ApprovalWorkflow, schema=ApprovalWorkflowSchema)
