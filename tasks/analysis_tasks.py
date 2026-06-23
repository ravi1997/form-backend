"""
tasks/analysis_tasks.py
Celery tasks for analysis execution with error isolation.
"""

import uuid
from datetime import datetime, timezone
from celery import current_task
from celery.exceptions import Ignore, Retry
from models.analysis import Analysis, AnalysisRun, AnalysisResult
from services.analysis_service import analysis_service
from engines.analysis_engine import AnalysisEngine
from logger.unified_logger import app_logger, error_logger, audit_logger
from utils.exceptions import NotFoundError, ValidationError, StateTransitionError
from celery import shared_task
import traceback


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def execute_analysis(self, analysis_id: str, organization_id: str, trigger: str = "manual", triggered_by: str = None):
    """
    Execute an analysis with error isolation and proper error handling.
    
    Args:
        analysis_id: ID of the analysis to execute
        organization_id: Organization ID
        trigger: Trigger type (manual, scheduled, reactive)
        triggered_by: User ID who triggered the execution
    """
    try:
        app_logger.info(f"Starting analysis execution: {analysis_id} for org {organization_id}")
        
        # Get analysis
        analysis = analysis_service.get_analysis(analysis_id, organization_id)
        
        # Create analysis run
        run = AnalysisRun(
            organization_id=organization_id,
            analysis_id=analysis,
            trigger=trigger,
            triggered_by=triggered_by,
            status="running",
            celery_task_id=self.request.id,
            started_at=datetime.now(timezone.utc)
        )
        run.save()
        
        # Update analysis status
        analysis.status = "running"
        analysis.save()
        
        # Execute analysis with error isolation
        engine = AnalysisEngine()
        execution_context = {
            "run_id": str(run.id),
            "organization_id": organization_id,
            "analysis_id": analysis_id,
            "node_results": {},
            "node_errors": {},
            "execution_order": [],
            "triggered_by": triggered_by
        }
        
        try:
            # Validate graph
            is_valid, errors = engine.validate_graph(analysis.graph)
            if not is_valid:
                raise ValidationError(f"Invalid analysis graph: {'; '.join(errors)}")
            
            # Get execution order
            nodes = analysis.graph['nodes']
            edges = analysis.graph['edges']
            execution_order = engine._get_execution_order(nodes, edges)
            
            # Execute nodes in batches with error isolation
            failed_nodes = []
            successful_nodes = []
            
            for node_batch in execution_order:
                batch_results = {}
                
                # Execute each node in the batch (they can run in parallel)
                for node_id in node_batch:
                    try:
                        node_config = next(n for n in nodes if n['id'] == node_id)
                        
                        # Update node status to running
                        if 'node_statuses' not in execution_context:
                            execution_context['node_statuses'] = {}
                        
                        execution_context['node_statuses'][node_id] = {
                            'status': 'running',
                            'started_at': datetime.now(timezone.utc).isoformat(),
                            'completed_at': None,
                            'error': None
                        }
                        
                        # Execute node
                        result = engine._execute_node(
                            node_id=node_id,
                            node_config=node_config,
                            execution_context=execution_context,
                            analysis=analysis
                        )
                        
                        # Store result
                        execution_context['node_results'][node_id] = result
                        execution_context['node_statuses'][node_id]['status'] = 'completed'
                        execution_context['node_statuses'][node_id]['completed_at'] = datetime.now(timezone.utc).isoformat()
                        
                        # Save result to database
                        analysis_result = AnalysisResult(
                            organization_id=organization_id,
                            analysis_id=analysis,
                            run_id=str(run.id),
                            node_id=node_id,
                            output_type=result.get('type', 'table'),
                            data=result,
                            row_count=result.get('row_count', 0),
                            column_definitions=result.get('columns', []),
                            cached_until=datetime.now(timezone.utc) + timedelta(hours=1)  # 1 hour cache
                        )
                        analysis_result.save()
                        
                        successful_nodes.append(node_id)
                        app_logger.info(f"Successfully executed node {node_id} of type {node_config['type']}")
                        
                    except Exception as node_error:
                        # Node failed but continue with other nodes (error isolation)
                        error_msg = str(node_error)
                        app_logger.error(f"Node {node_id} failed: {error_msg}")
                        
                        execution_context['node_errors'][node_id] = error_msg
                        execution_context['node_statuses'][node_id]['status'] = 'failed'
                        execution_context['node_statuses'][node_id]['error'] = error_msg
                        execution_context['node_statuses'][node_id]['completed_at'] = datetime.now(timezone.utc).isoformat()
                        
                        # Save error result
                        error_result = {
                            "type": "error",
                            "error": error_msg,
                            "node_id": node_id,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                        
                        analysis_result = AnalysisResult(
                            organization_id=organization_id,
                            analysis_id=analysis,
                            run_id=str(run.id),
                            node_id=node_id,
                            output_type="error",
                            data=error_result,
                            cached_until=datetime.now(timezone.utc) + timedelta(hours=1)
                        )
                        analysis_result.save()
                        
                        failed_nodes.append(node_id)
                
                batch_results.update(execution_context['node_results'])
            
            # Determine overall run status
            if failed_nodes:
                if successful_nodes:
                    run_status = "partial"  # Some nodes succeeded, some failed
                    error_summary = f"Partial success: {len(successful_nodes)} nodes succeeded, {len(failed_nodes)} nodes failed"
                else:
                    run_status = "failed"
                    error_summary = f"All nodes failed: {len(failed_nodes)} nodes failed"
            else:
                run_status = "completed"
                error_summary = None
            
            # Update run status
            run.status = run_status
            run.completed_at = datetime.now(timezone.utc)
            if run.started_at:
                run.execution_time_seconds = (run.completed_at - run.started_at).total_seconds()
            run.node_statuses = execution_context['node_statuses']
            run.error_summary = error_summary
            run.save()
            
            # Update analysis status
            analysis.status = "idle" if run_status == "completed" else "error"
            analysis.last_run_id = run
            analysis.save()
            
            audit_logger.info(
                f"Analysis execution completed: {analysis_id}, run {run.id}, "
                f"status={run_status}, successful_nodes={len(successful_nodes)}, "
                f"failed_nodes={len(failed_nodes)}"
            )
            
            return {
                "run_id": str(run.id),
                "status": run_status,
                "successful_nodes": len(successful_nodes),
                "failed_nodes": len(failed_nodes),
                "execution_time_seconds": run.execution_time_seconds
            }
            
        except Exception as execution_error:
            # Handle execution-level errors
            error_msg = str(execution_error)
            error_logger.error(f"Analysis execution failed: {error_msg}", exc_info=True)
            
            # Update run status
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            if run.started_at:
                run.execution_time_seconds = (run.completed_at - run.started_at).total_seconds()
            run.error_summary = error_msg
            run.save()
            
            # Update analysis status
            analysis.status = "error"
            analysis.last_run_id = run
            analysis.save()
            
            audit_logger.error(
                f"Analysis execution failed: {analysis_id}, run {run.id}, error={error_msg}"
            )
            
            raise
            
    except NotFoundError as e:
        error_logger.error(f"Analysis not found: {analysis_id}")
        raise Ignore()
        
    except ValidationError as e:
        error_logger.error(f"Validation error for analysis {analysis_id}: {str(e)}")
        # Don't retry validation errors
        raise Ignore()
        
    except Exception as e:
        error_logger.error(f"Unexpected error in analysis execution: {str(e)}", exc_info=True)
        
        # Retry for transient errors
        if self.request.retries < self.max_retries:
            error_logger.info(f"Retrying analysis execution: {analysis_id}, attempt {self.request.retries + 1}")
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        else:
            error_logger.error(f"Max retries exceeded for analysis: {analysis_id}")
            raise Ignore()


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def execute_scheduled_analysis(self, analysis_id: str, organization_id: str):
    """
    Execute a scheduled analysis.
    
    Args:
        analysis_id: ID of the analysis to execute
        organization_id: Organization ID
    """
    try:
        app_logger.info(f"Executing scheduled analysis: {analysis_id} for org {organization_id}")
        
        # Check if analysis exists and supports scheduled execution
        analysis = analysis_service.get_analysis(analysis_id, organization_id)
        
        if "scheduled" not in analysis.execution_modes:
            app_logger.warning(f"Analysis {analysis_id} does not support scheduled execution")
            return
        
        # Check if analysis is already running
        if analysis.status == "running":
            app_logger.warning(f"Analysis {analysis_id} is already running, skipping scheduled execution")
            return
        
        # Execute the analysis
        execute_analysis.delay(
            analysis_id=analysis_id,
            organization_id=organization_id,
            trigger="scheduled"
        )
        
    except NotFoundError:
        error_logger.error(f"Scheduled analysis not found: {analysis_id}")
        raise Ignore()
        
    except Exception as e:
        error_logger.error(f"Error in scheduled analysis execution: {str(e)}", exc_info=True)
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=30 * (2 ** self.request.retries))
        else:
            error_logger.error(f"Max retries exceeded for scheduled analysis: {analysis_id}")
            raise Ignore()


@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def trigger_reactive_analysis(self, analysis_id: str, organization_id: str, event_data: dict = None):
    """
    Trigger reactive execution of an analysis.
    
    Args:
        analysis_id: ID of the analysis to execute
        organization_id: Organization ID
        event_data: Event data that triggered the reactive execution
    """
    try:
        app_logger.info(f"Triggering reactive analysis: {analysis_id} for org {organization_id}")
        
        # Check if analysis exists and supports reactive execution
        analysis = analysis_service.get_analysis(analysis_id, organization_id)
        
        if "reactive" not in analysis.execution_modes:
            app_logger.warning(f"Analysis {analysis_id} does not support reactive execution")
            return
        
        # Trigger the analysis with debounce handling
        analysis_service.trigger_reactive_execution(
            analysis_id=analysis_id,
            organization_id=organization_id,
            event_data=event_data
        )
        
    except StateTransitionError as e:
        # Debounced or other state error - don't retry
        app_logger.info(f"Reactive analysis not triggered: {str(e)}")
        raise Ignore()
        
    except NotFoundError:
        error_logger.error(f"Reactive analysis not found: {analysis_id}")
        raise Ignore()
        
    except Exception as e:
        error_logger.error(f"Error in reactive analysis trigger: {str(e)}", exc_info=True)
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=10 * (2 ** self.request.retries))
        else:
            error_logger.error(f"Max retries exceeded for reactive analysis: {analysis_id}")
            raise Ignore()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def cleanup_old_analysis_results(self):
    """
    Cleanup old analysis results and exports.
    This task should be scheduled to run periodically (e.g., daily).
    """
    try:
        from datetime import datetime, timezone, timedelta
        
        app_logger.info("Starting cleanup of old analysis results")
        
        # Delete results older than 30 days
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        
        # Clean up analysis results
        old_results = AnalysisResult.objects(created_at__lt=cutoff_date)
        results_count = old_results.count()
        old_results.delete()
        
        # Clean up analysis runs older than 90 days
        runs_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        old_runs = AnalysisRun.objects(created_at__lt=runs_cutoff)
        runs_count = old_runs.count()
        old_runs.delete()
        
        app_logger.info(f"Cleanup completed: deleted {results_count} results and {runs_count} runs")
        
        return {
            "results_deleted": results_count,
            "runs_deleted": runs_count,
            "cutoff_date": cutoff_date.isoformat()
        }
        
    except Exception as e:
        error_logger.error(f"Error in analysis results cleanup: {str(e)}", exc_info=True)
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        else:
            error_logger.error(f"Max retries exceeded for analysis cleanup")
            raise Ignore()


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def cache_analysis_results(self, analysis_id: str, organization_id: str, run_id: str):
    """
    Cache analysis results for faster access.
    
    Args:
        analysis_id: ID of the analysis
        organization_id: Organization ID
        run_id: ID of the analysis run
    """
    try:
        from extensions import redis_client
        import json
        
        app_logger.info(f"Caching analysis results: {analysis_id}, run {run_id}")
        
        # Get results from database
        results = AnalysisResult.objects(
            analysis_id=analysis_id,
            run_id=run_id,
            organization_id=organization_id
        )
        
        # Build cache data
        cache_data = {
            "analysis_id": analysis_id,
            "run_id": run_id,
            "results": [],
            "cached_at": datetime.now(timezone.utc).isoformat()
        }
        
        for result in results:
            cache_data["results"].append({
                "node_id": result.node_id,
                "output_type": result.output_type,
                "data": result.data,
                "row_count": result.row_count,
                "column_definitions": result.column_definitions
            })
        
        # Cache in Redis for 1 hour
        cache_key = f"analysis_results:{organization_id}:{analysis_id}:{run_id}"
        redis_client.setex(cache_key, 3600, json.dumps(cache_data))
        
        app_logger.info(f"Successfully cached analysis results: {cache_key}")
        
        return {
            "cache_key": cache_key,
            "results_count": len(cache_data["results"]),
            "cache_ttl": 3600
        }
        
    except Exception as e:
        error_logger.error(f"Error caching analysis results: {str(e)}", exc_info=True)
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=30 * (2 ** self.request.retries))
        else:
            error_logger.error(f"Max retries exceeded for caching analysis results")
            raise Ignore()


# Scheduler task registration
def register_scheduled_analysis(analysis_id: str, schedule: str):
    """
    Register a scheduled analysis with Celery beat.
    
    Args:
        analysis_id: ID of the analysis
        schedule: Cron schedule expression
    """
    try:
        from celery.beat import SchedulerEntry
        from celery.schedules import crontab
        
        # Parse cron schedule
        minute, hour, day, month, day_of_week = schedule.split()
        
        # Create crontab schedule
        schedule_obj = crontab(
            minute=minute,
            hour=hour,
            day_of_month=day,
            month_of_year=month,
            day_of_week=day_of_week
        )
        
        # Create scheduler entry
        entry = SchedulerEntry(
            name=f"analysis_{analysis_id}",
            task=execute_scheduled_analysis.name,
            schedule=schedule_obj,
            args=[analysis_id],
            kwargs={}
        )
        
        # In production, this would be saved to celery beat schedule
        app_logger.info(f"Registered scheduled analysis: {analysis_id} with schedule {schedule}")
        
        return entry
        
    except Exception as e:
        error_logger.error(f"Error registering scheduled analysis {analysis_id}: {str(e)}")
        raise