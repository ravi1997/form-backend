"""
services/analysis_service.py
Analysis service with CRUD operations and execution logic for the Form Builder Platform.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from mongoengine import QuerySet
from models.analysis import Analysis, AnalysisRun, AnalysisResult, AnalysisExport
from models.form import Form
from models.response import FormResponse
from services.base import BaseService
from engines.analysis_engine import AnalysisEngine
from services.analysis_run_service import AnalysisRunService
from services.export_job_service import ExportJobService
from utils.exceptions import NotFoundError, ValidationError, StateTransitionError
from logger.unified_logger import app_logger, error_logger, audit_logger
from extensions import redis_client
from schemas.analysis import AnalysisCreateSchema, AnalysisUpdateSchema
import json
import networkx as nx


class AnalysisService(BaseService):
    """Service for analysis operations."""

    def __init__(self):
        super().__init__(model=Analysis, schema=AnalysisCreateSchema)
        self.analysis_engine = AnalysisEngine()
        self.run_service = AnalysisRunService()
        self.export_service = ExportJobService()

    def create_analysis(self, schema: AnalysisCreateSchema, organization_id: str, created_by: str) -> Analysis:
        """Create a new analysis."""
        try:
            # Validate the graph structure
            is_valid, errors = self.analysis_engine.validate_graph(schema.graph)
            if not is_valid:
                raise ValidationError(f"Invalid analysis graph: {'; '.join(errors)}")

            # Create analysis
            analysis = Analysis(
                organization_id=organization_id,
                project_id=schema.project_id,
                name=schema.name,
                description=schema.description,
                linked_form_ids=schema.linked_form_ids or [],
                execution_modes=schema.execution_modes or ["on_demand"],
                schedule=schema.schedule,
                reactive_debounce_ms=schema.reactive_debounce_ms or 1000,
                graph=schema.graph,
                created_by=created_by
            )
            analysis.save()

            audit_logger.info(
                f"Analysis created: ID={analysis.id}, Name='{analysis.name}', "
                f"OrgID={organization_id}, ProjectID={schema.project_id}"
            )
            
            return analysis
            
        except Exception as e:
            error_logger.error(f"Create analysis error: {str(e)}", exc_info=True)
            raise

    def get_analysis(self, analysis_id: str, organization_id: str) -> Analysis:
        """Get an analysis by ID."""
        analysis = self.model.objects(
            id=analysis_id, 
            organization_id=organization_id, 
            is_deleted=False
        ).first()
        
        if not analysis:
            raise NotFoundError(f"Analysis {analysis_id} not found")
        
        return analysis

    def list_analyses(
        self, 
        organization_id: str, 
        project_id: str = None,
        page: int = 1, 
        page_size: int = 50
    ) -> Tuple[List[Analysis], int]:
        """List analyses with pagination."""
        query = self.model.objects(
            organization_id=organization_id, 
            is_deleted=False
        )
        
        if project_id:
            query = query.filter(project_id=project_id)
        
        total = query.count()
        analyses = query.skip((page - 1) * page_size).limit(page_size).order_by('-created_at')
        
        return list(analyses), total

    def update_analysis(self, analysis_id: str, schema: AnalysisUpdateSchema, organization_id: str) -> Analysis:
        """Update an analysis."""
        analysis = self.get_analysis(analysis_id, organization_id)
        
        # Validate the graph structure if provided
        if schema.graph:
            is_valid, errors = self.analysis_engine.validate_graph(schema.graph)
            if not is_valid:
                raise ValidationError(f"Invalid analysis graph: {'; '.join(errors)}")
        
        # Update fields
        update_data = schema.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(analysis, field, value)
        
        analysis.updated_at = datetime.now(timezone.utc)
        analysis.save()
        
        audit_logger.info(
            f"Analysis updated: ID={analysis_id}, Name='{analysis.name}', OrgID={organization_id}"
        )
        
        return analysis

    def delete_analysis(self, analysis_id: str, organization_id: str) -> None:
        """Delete an analysis."""
        analysis = self.get_analysis(analysis_id, organization_id)
        
        # Soft delete
        analysis.is_deleted = True
        analysis.updated_at = datetime.now(timezone.utc)
        analysis.save()
        
        # Clear cache
        self._clear_analysis_cache(analysis_id, organization_id)
        
        audit_logger.info(
            f"Analysis deleted: ID={analysis_id}, Name='{analysis.name}', OrgID={organization_id}"
        )

    def execute_analysis(
        self, 
        analysis_id: str, 
        organization_id: str, 
        trigger: str = "manual",
        triggered_by: str = None
    ) -> AnalysisRun:
        """Execute an analysis."""
        analysis = self.get_analysis(analysis_id, organization_id)
        
        # Check if analysis can be executed
        if analysis.status == "running":
            raise StateTransitionError("Analysis is already running")
        
        # Update analysis status
        analysis.status = "running"
        analysis.save()
        
        try:
            # Execute the analysis
            run = self.analysis_engine.execute_analysis(
                analysis=analysis,
                organization_id=organization_id,
                trigger=trigger,
                triggered_by=triggered_by
            )
            
            # Update analysis with last run
            analysis.last_run_id = run
            analysis.status = "idle" if run.status == "completed" else "error"
            analysis.save()
            
            return run
            
        except Exception as e:
            # Reset analysis status on error
            analysis.status = "error"
            analysis.save()
            raise

    def get_analysis_results(
        self, 
        analysis_id: str, 
        run_id: str = None, 
        organization_id: str = None
    ) -> List[AnalysisResult]:
        """Get analysis results."""
        query = AnalysisResult.objects(analysis_id=analysis_id)
        
        if organization_id:
            query = query.filter(organization_id=organization_id)
        
        if run_id:
            query = query.filter(run_id=run_id)
        
        return list(query.order_by('-created_at'))

    def create_export(
        self,
        analysis_id: str,
        organization_id: str,
        format: str,
        node_ids: List[str] = None,
        run_id: str = None,
        created_by: str = None
    ) -> AnalysisExport:
        """Create an export job."""
        analysis = self.get_analysis(analysis_id, organization_id)
        
        # Create export job
        export = AnalysisExport(
            organization_id=organization_id,
            analysis_id=analysis,
            format=format,
            node_ids=node_ids or [],
            run_id=run_id,
            status="queued",
            created_by=created_by,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7)  # 7 days TTL
        )
        export.save()
        
        # Queue export job
        from tasks.analysis_tasks import generate_export
        generate_export.delay(str(export.id))
        
        audit_logger.info(
            f"Analysis export created: ID={export.id}, AnalysisID={analysis_id}, "
            f"Format={format}, OrgID={organization_id}"
        )
        
        return export

    def get_export(self, export_id: str, organization_id: str) -> AnalysisExport:
        """Get an export by ID."""
        export = AnalysisExport.objects(
            id=export_id, 
            organization_id=organization_id, 
            is_deleted=False
        ).first()
        
        if not export:
            raise NotFoundError(f"Export {export_id} not found")
        
        return export

    def schedule_analysis(self, analysis_id: str, organization_id: str, schedule: str) -> Analysis:
        """Schedule an analysis for execution."""
        analysis = self.get_analysis(analysis_id, organization_id)
        
        # Validate cron expression
        from celery.schedules import crontab
        try:
            # Simple validation - in production, use proper cron parser
            if not schedule or len(schedule.split()) != 5:
                raise ValidationError("Invalid cron expression")
        except Exception:
            raise ValidationError("Invalid cron expression")
        
        # Update analysis
        analysis.schedule = schedule
        if "scheduled" not in analysis.execution_modes:
            analysis.execution_modes.append("scheduled")
        analysis.updated_at = datetime.now(timezone.utc)
        analysis.save()
        
        # Register with Celery beat
        from tasks.scheduler import register_scheduled_analysis
        register_scheduled_analysis(str(analysis.id), schedule)
        
        audit_logger.info(
            f"Analysis scheduled: ID={analysis_id}, Schedule='{schedule}', OrgID={organization_id}"
        )
        
        return analysis

    def trigger_reactive_execution(
        self, 
        analysis_id: str, 
        organization_id: str,
        event_data: Dict[str, Any] = None
    ) -> AnalysisRun:
        """Trigger reactive execution of an analysis."""
        analysis = self.get_analysis(analysis_id, organization_id)
        
        if "reactive" not in analysis.execution_modes:
            raise StateTransitionError("Analysis does not support reactive execution")
        
        # Debounce check
        debounce_key = f"analysis_reactive_debounce:{analysis_id}"
        last_trigger = redis_client.get(debounce_key)
        
        if last_trigger:
            last_trigger_time = datetime.fromisoformat(last_trigger.decode())
            debounce_period = timedelta(milliseconds=analysis.reactive_debounce_ms)
            if datetime.now(timezone.utc) - last_trigger_time < debounce_period:
                raise StateTransitionError("Analysis execution debounced")
        
        # Set debounce key
        redis_client.setex(
            debounce_key, 
            analysis.reactive_debounce_ms // 1000, 
            datetime.now(timezone.utc).isoformat()
        )
        
        # Execute analysis
        return self.execute_analysis(
            analysis_id=analysis_id,
            organization_id=organization_id,
            trigger="reactive"
        )

    def _clear_analysis_cache(self, analysis_id: str, organization_id: str) -> None:
        """Clear analysis cache."""
        cache_keys = [
            f"analysis_results:{organization_id}:{analysis_id}",
            f"analysis_run:{organization_id}:{analysis_id}",
            f"analysis_graph:{organization_id}:{analysis_id}"
        ]
        
        for key in cache_keys:
            try:
                redis_client.delete(key)
            except Exception as e:
                app_logger.warning(f"Failed to clear cache key {key}: {e}")

    def get_analysis_stats(self, analysis_id: str, organization_id: str) -> Dict[str, Any]:
        """Get analysis statistics."""
        analysis = self.get_analysis(analysis_id, organization_id)
        
        # Get run statistics
        total_runs = AnalysisRun.objects(analysis_id=analysis).count()
        successful_runs = AnalysisRun.objects(
            analysis_id=analysis, 
            status="completed"
        ).count()
        failed_runs = AnalysisRun.objects(
            analysis_id=analysis, 
            status="failed"
        ).count()
        
        # Get average execution time
        successful_run_docs = AnalysisRun.objects(
            analysis_id=analysis, 
            status="completed",
            execution_time_seconds__exists=True
        )
        
        avg_execution_time = 0
        if successful_run_docs.count() > 0:
            total_time = sum(run.execution_time_seconds for run in successful_run_docs)
            avg_execution_time = total_time / successful_run_docs.count()
        
        return {
            "analysis_id": str(analysis.id),
            "name": analysis.name,
            "status": analysis.status,
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "success_rate": (successful_runs / total_runs * 100) if total_runs > 0 else 0,
            "average_execution_time": round(avg_execution_time, 2),
            "last_run": analysis.last_run_id.created_at if analysis.last_run_id else None,
            "execution_modes": analysis.execution_modes,
            "schedule": analysis.schedule
        }


# Global service instance
analysis_service = AnalysisService()