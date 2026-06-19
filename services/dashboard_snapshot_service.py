"""
services/dashboard_snapshot_service.py
Dashboard snapshot service for historical views and data preservation.
"""

from models.dashboard import DashboardSnapshot, Dashboard, DashboardPublicAccess
from services.base import BaseService
from schemas.base import InboundPayloadSchema
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from logger.unified_logger import app_logger, error_logger, audit_logger
import uuid
import secrets


class SnapshotCreateSchema(BaseModel, InboundPayloadSchema):
    dashboard_id: str
    name: str
    description: Optional[str] = None
    expires_in_hours: Optional[int] = None  # Hours until snapshot expires
    is_public: bool = False


class SnapshotSchema(BaseModel):
    id: str
    dashboard_id: str
    name: str
    description: Optional[str] = None
    snapshot_data: Dict[str, Any]
    widget_states: Dict[str, Any]
    filter_states: Dict[str, Any]
    created_at: str
    expires_at: Optional[str] = None
    is_public_snapshot: bool
    snapshot_token: Optional[str] = None
    access_count: int = 0


class DashboardSnapshotService(BaseService):
    """Service for managing dashboard snapshots."""

    def __init__(self):
        super().__init__(model=DashboardSnapshot, schema=SnapshotSchema)

    def _generate_snapshot_token(self) -> str:
        """Generate a secure token for snapshot access."""
        return secrets.token_urlsafe(32)

    def create_snapshot(self, snapshot_data: SnapshotCreateSchema, user_id: str, organization_id: str) -> SnapshotSchema:
        """Create a new dashboard snapshot."""
        app_logger.debug(f"Entering create_snapshot: {snapshot_data.name} for dashboard {snapshot_data.dashboard_id}")
        
        try:
            # Get the dashboard
            dashboard = Dashboard.objects(
                id=snapshot_data.dashboard_id, 
                organization_id=organization_id, 
                is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"Dashboard not found for snapshot: {snapshot_data.dashboard_id}")
                raise NotFoundError(f"Dashboard {snapshot_data.dashboard_id} not found")
            
            # Calculate expiration time
            expires_at = None
            if snapshot_data.expires_in_hours:
                expires_at = datetime.now(timezone.utc) + timedelta(hours=snapshot_data.expires_in_hours)
            
            # Generate snapshot token if public
            snapshot_token = None
            if snapshot_data.is_public:
                snapshot_token = self._generate_snapshot_token()
            
            # Create snapshot
            snapshot = DashboardSnapshot(
                organization_id=organization_id,
                dashboard_id=dashboard,
                name=snapshot_data.name,
                description=snapshot_data.description,
                snapshot_data=self._capture_dashboard_state(dashboard),
                widget_states=self._capture_widget_states(dashboard),
                filter_states=self._capture_filter_states(dashboard),
                created_by=user_id,
                expires_at=expires_at,
                is_public_snapshot=snapshot_data.is_public,
                snapshot_token=snapshot_token
            )
            
            snapshot.save()
            
            audit_logger.info(
                f"Audit: dashboard snapshot created {snapshot.id} for dashboard {snapshot_data.dashboard_id} by user {user_id}"
            )
            
            result = self._snapshot_to_schema(snapshot)
            app_logger.debug(f"Exiting create_snapshot: {snapshot_data.name} successfully")
            return result
            
        except Exception as e:
            error_logger.error(
                f"Error in create_snapshot {snapshot_data.name}: {str(e)}", exc_info=True
            )
            raise

    def _capture_dashboard_state(self, dashboard: Dashboard) -> Dict[str, Any]:
        """Capture the current state of a dashboard."""
        from services.dashboard_service import DashboardService
        
        dashboard_service = DashboardService()
        return dashboard_service._dashboard_snapshot(dashboard)

    def _capture_widget_states(self, dashboard: Dashboard) -> Dict[str, Any]:
        """Capture individual widget states."""
        widget_states = {}
        
        for widget in dashboard.widgets or []:
            widget_states[widget.id] = {
                "widget_type": widget.widget_type,
                "title": widget.title,
                "position": {
                    "x": widget.position.x,
                    "y": widget.position.y,
                    "width": widget.position.width,
                    "height": widget.position.height,
                    "z_index": widget.position.z_index
                },
                "is_visible": widget.is_visible,
                "is_locked": widget.is_locked,
                "data_source": {
                    "analysis_id": str(widget.data_source.analysis_id) if widget.data_source.analysis_id else None,
                    "node_id": widget.data_source.node_id,
                    "refresh_mode": widget.data_source.refresh_mode
                } if widget.data_source else None,
                "config": {
                    "chart_type": widget.config.chart_type,
                    "aggregation_type": widget.config.aggregation_type,
                    "show_legend": widget.config.show_legend,
                    "show_labels": widget.config.show_labels
                } if widget.config else None
            }
        
        return widget_states

    def _capture_filter_states(self, dashboard: Dashboard) -> Dict[str, Any]:
        """Capture filter states."""
        filter_states = {}
        
        for filter_obj in dashboard.filters or []:
            filter_states[filter_obj.id] = {
                "name": filter_obj.name,
                "filter_type": filter_obj.filter_type,
                "field_name": filter_obj.field_name,
                "default_value": filter_obj.default_value,
                "is_required": filter_obj.is_required,
                "affects_widgets": filter_obj.affects_widgets
            }
        
        return filter_states

    def _snapshot_to_schema(self, snapshot: DashboardSnapshot) -> SnapshotSchema:
        """Convert snapshot object to schema."""
        return SnapshotSchema(
            id=str(snapshot.id),
            dashboard_id=str(snapshot.dashboard_id.id),
            name=snapshot.name,
            description=snapshot.description,
            snapshot_data=snapshot.snapshot_data,
            widget_states=snapshot.widget_states,
            filter_states=snapshot.filter_states,
            created_at=snapshot.created_at.isoformat(),
            expires_at=snapshot.expires_at.isoformat() if snapshot.expires_at else None,
            is_public_snapshot=snapshot.is_public_snapshot,
            snapshot_token=snapshot.snapshot_token,
            access_count=0  # Will be updated when accessed
        )

    def get_snapshot(self, snapshot_id: str, organization_id: str) -> SnapshotSchema:
        """Get snapshot by ID."""
        app_logger.debug(f"Entering get_snapshot: {snapshot_id} (org: {organization_id})")
        
        try:
            snapshot = self.model.objects(
                id=snapshot_id, 
                organization_id=organization_id, 
                is_deleted=False
            ).first()
            
            if not snapshot:
                from .exceptions import NotFoundError
                app_logger.warning(f"Snapshot not found: {snapshot_id} (org: {organization_id})")
                raise NotFoundError(f"Snapshot {snapshot_id} not found")
            
            # Check if snapshot has expired
            if snapshot.expires_at and snapshot.expires_at < datetime.now(timezone.utc):
                from .exceptions import ValidationError
                app_logger.warning(f"Snapshot expired: {snapshot_id}")
                raise ValidationError(f"Snapshot {snapshot_id} has expired")
            
            result = self._snapshot_to_schema(snapshot)
            app_logger.debug(f"Exiting get_snapshot: {snapshot_id} successfully")
            return result
            
        except Exception as e:
            if not isinstance(e, (NotFoundError, ValidationError)):
                error_logger.error(
                    f"Error in get_snapshot {snapshot_id}: {str(e)}", exc_info=True
                )
            raise

    def get_public_snapshot(self, snapshot_token: str) -> SnapshotSchema:
        """Get public snapshot by token."""
        app_logger.debug(f"Entering get_public_snapshot: token {snapshot_token[:8]}...")
        
        try:
            snapshot = self.model.objects(
                snapshot_token=snapshot_token,
                is_public_snapshot=True,
                is_deleted=False
            ).first()
            
            if not snapshot:
                from .exceptions import NotFoundError
                app_logger.warning(f"Public snapshot not found: token {snapshot_token[:8]}...")
                raise NotFoundError("Public snapshot not found")
            
            # Check if snapshot has expired
            if snapshot.expires_at and snapshot.expires_at < datetime.now(timezone.utc):
                from .exceptions import ValidationError
                app_logger.warning(f"Public snapshot expired: token {snapshot_token[:8]}...")
                raise ValidationError("Public snapshot has expired")
            
            result = self._snapshot_to_schema(snapshot)
            app_logger.debug(f"Exiting get_public_snapshot: token {snapshot_token[:8]}... successfully")
            return result
            
        except Exception as e:
            if not isinstance(e, (NotFoundError, ValidationError)):
                error_logger.error(
                    f"Error in get_public_snapshot {snapshot_token[:8]}...: {str(e)}", exc_info=True
                )
            raise

    def list_snapshots(self, dashboard_id: str, organization_id: str) -> List[SnapshotSchema]:
        """List snapshots for a dashboard."""
        app_logger.debug(f"Entering list_snapshots: dashboard {dashboard_id} (org: {organization_id})")
        
        try:
            # Verify dashboard exists
            dashboard = Dashboard.objects(
                id=dashboard_id, 
                organization_id=organization_id, 
                is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"Dashboard not found for snapshots: {dashboard_id} (org: {organization_id})")
                raise NotFoundError(f"Dashboard {dashboard_id} not found")
            
            # Get snapshots
            snapshots = self.model.objects(
                dashboard_id=dashboard,
                organization_id=organization_id,
                is_deleted=False
            ).order_by("-created_at")
            
            result = [self._snapshot_to_schema(snapshot) for snapshot in snapshots]
            app_logger.debug(f"Exiting list_snapshots: found {len(result)} snapshots")
            return result
            
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in list_snapshots {dashboard_id}: {str(e)}", exc_info=True
                )
            raise

    def delete_snapshot(self, snapshot_id: str, organization_id: str, user_id: str) -> bool:
        """Delete a snapshot."""
        app_logger.debug(f"Entering delete_snapshot: {snapshot_id} (org: {organization_id})")
        
        try:
            snapshot = self.model.objects(
                id=snapshot_id, 
                organization_id=organization_id, 
                is_deleted=False
            ).first()
            
            if not snapshot:
                from .exceptions import NotFoundError
                app_logger.warning(f"Snapshot not found for deletion: {snapshot_id} (org: {organization_id})")
                raise NotFoundError(f"Snapshot {snapshot_id} not found")
            
            snapshot.is_deleted = True
            snapshot.deleted_at = datetime.now(timezone.utc)
            snapshot.save()
            
            audit_logger.info(
                f"Audit: snapshot deleted {snapshot_id} (org: {organization_id}) by user {user_id}"
            )
            
            app_logger.debug(f"Exiting delete_snapshot: {snapshot_id} successfully")
            return True
            
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in delete_snapshot {snapshot_id}: {str(e)}", exc_info=True
                )
            raise

    def cleanup_expired_snapshots(self, organization_id: Optional[str] = None) -> int:
        """Clean up expired snapshots."""
        app_logger.debug("Entering cleanup_expired_snapshots")
        
        try:
            query = self.model.objects(is_deleted=False)
            
            if organization_id:
                query = query.filter(organization_id=organization_id)
            
            # Find expired snapshots
            expired_snapshots = query.filter(expires_at__lt=datetime.now(timezone.utc))
            count = expired_snapshots.count()
            
            if count > 0:
                expired_snapshots.update(is_deleted=True, deleted_at=datetime.now(timezone.utc))
                app_logger.info(f"Cleaned up {count} expired snapshots")
            
            app_logger.debug(f"Exiting cleanup_expired_snapshots: cleaned {count} snapshots")
            return count
            
        except Exception as e:
            error_logger.error(
                f"Error in cleanup_expired_snapshots: {str(e)}", exc_info=True
            )
            raise