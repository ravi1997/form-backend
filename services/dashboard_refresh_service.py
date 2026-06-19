from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
from celery import Celery
from celery.schedules import crontab
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
import redis
import json

from models.dashboard import DashboardModel
from services.dashboard_service import DashboardService
from services.widget_data_binding_service import WidgetDataBindingService
from services.analysis_service import AnalysisService
from config.celery import celery_app

logger = logging.getLogger(__name__)


class DashboardRefreshService:
    """Service for managing dashboard auto-refresh functionality."""
    
    def __init__(self):
        self.redis_client = redis.Redis.from_url('redis://localhost:6379/0')
        self.dashboard_service = DashboardService()
        self.widget_binding_service = WidgetDataBindingService()
        self.analysis_service = AnalysisService()
        
        # Initialize APScheduler for background refresh
        self.scheduler = BackgroundScheduler(
            jobstores={
                'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')
            },
            executors={
                'default': ThreadPoolExecutor(20)
            },
            job_defaults={
                'coalesce': False,
                'max_instances': 3
            }
        )
        
    def start_scheduler(self):
        """Start the background scheduler."""
        try:
            self.scheduler.start()
            logger.info("Dashboard refresh scheduler started")
        except Exception as e:
            logger.error(f"Failed to start dashboard refresh scheduler: {e}")
            
    def stop_scheduler(self):
        """Stop the background scheduler."""
        try:
            self.scheduler.shutdown()
            logger.info("Dashboard refresh scheduler stopped")
        except Exception as e:
            logger.error(f"Failed to stop dashboard refresh scheduler: {e}")
    
    def schedule_dashboard_refresh(self, dashboard_id: str, refresh_config: Dict[str, Any]):
        """Schedule auto-refresh for a dashboard."""
        try:
            # Remove existing jobs for this dashboard
            self._remove_dashboard_jobs(dashboard_id)
            
            # Schedule based on refresh mode
            refresh_mode = refresh_config.get('mode', 'manual')
            
            if refresh_mode == 'interval':
                interval_seconds = refresh_config.get('interval_seconds', 300)
                self._schedule_interval_refresh(dashboard_id, interval_seconds)
            elif refresh_mode == 'cron':
                cron_expression = refresh_config.get('cron_expression', '0 */5 * * *')
                self._schedule_cron_refresh(dashboard_id, cron_expression)
            elif refresh_mode == 'with_analysis':
                analysis_ids = refresh_config.get('analysis_ids', [])
                self._schedule_analysis_dependent_refresh(dashboard_id, analysis_ids)
                
            logger.info(f"Scheduled refresh for dashboard {dashboard_id} with mode: {refresh_mode}")
            
        except Exception as e:
            logger.error(f"Failed to schedule refresh for dashboard {dashboard_id}: {e}")
            
    def _remove_dashboard_jobs(self, dashboard_id: str):
        """Remove all scheduled jobs for a dashboard."""
        try:
            jobs_to_remove = []
            for job in self.scheduler.get_jobs():
                if job.id and job.id.startswith(f"dashboard_{dashboard_id}_"):
                    jobs_to_remove.append(job.id)
                    
            for job_id in jobs_to_remove:
                self.scheduler.remove_job(job_id)
                
            logger.debug(f"Removed {len(jobs_to_remove)} jobs for dashboard {dashboard_id}")
            
        except Exception as e:
            logger.error(f"Failed to remove jobs for dashboard {dashboard_id}: {e}")
    
    def _schedule_interval_refresh(self, dashboard_id: str, interval_seconds: int):
        """Schedule interval-based refresh."""
        job_id = f"dashboard_{dashboard_id}_interval"
        
        self.scheduler.add_job(
            func=refresh_dashboard_data,
            trigger=IntervalTrigger(seconds=interval_seconds),
            args=[dashboard_id],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300  # 5 minutes grace time
        )
        
    def _schedule_cron_refresh(self, dashboard_id: str, cron_expression: str):
        """Schedule cron-based refresh."""
        job_id = f"dashboard_{dashboard_id}_cron"
        
        # Parse cron expression (simplified - in production use proper cron parser)
        parts = cron_expression.split()
        if len(parts) == 5:
            minute, hour, day, month, day_of_week = parts
            
            self.scheduler.add_job(
                func=refresh_dashboard_data,
                trigger=CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week
                ),
                args=[dashboard_id],
                id=job_id,
                replace_existing=True,
                misfire_grace_time=300
            )
    
    def _schedule_analysis_dependent_refresh(self, dashboard_id: str, analysis_ids: list):
        """Schedule refresh that triggers when analyses complete."""
        job_id = f"dashboard_{dashboard_id}_analysis_dependent"
        
        # This would typically listen for analysis completion events
        # For now, we'll schedule a regular check
        self.scheduler.add_job(
            func=check_analysis_and_refresh_dashboard,
            trigger=IntervalTrigger(seconds=60),  # Check every minute
            args=[dashboard_id, analysis_ids],
            id=job_id,
            replace_existing=True
        )
    
    def trigger_manual_refresh(self, dashboard_id: str):
        """Trigger an immediate manual refresh of dashboard data."""
        try:
            # Queue the refresh task
            refresh_dashboard_data.delay(dashboard_id)
            logger.info(f"Triggered manual refresh for dashboard {dashboard_id}")
            
            # Update last refresh time in Redis
            self.redis_client.setex(
                f"dashboard:last_refresh:{dashboard_id}",
                86400,  # 24 hours TTL
                datetime.utcnow().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Failed to trigger manual refresh for dashboard {dashboard_id}: {e}")
    
    def get_refresh_status(self, dashboard_id: str) -> Dict[str, Any]:
        """Get the refresh status for a dashboard."""
        try:
            # Get job information
            jobs = []
            for job in self.scheduler.get_jobs():
                if job.id and job.id.startswith(f"dashboard_{dashboard_id}_"):
                    jobs.append({
                        'id': job.id,
                        'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                        'trigger': str(job.trigger)
                    })
            
            # Get last refresh time from Redis
            last_refresh = self.redis_client.get(f"dashboard:last_refresh:{dashboard_id}")
            last_refresh_time = datetime.fromisoformat(last_refresh.decode()) if last_refresh else None
            
            # Get refresh count
            refresh_count = self.redis_client.get(f"dashboard:refresh_count:{dashboard_id}")
            refresh_count = int(refresh_count.decode()) if refresh_count else 0
            
            return {
                'dashboard_id': dashboard_id,
                'scheduled_jobs': jobs,
                'last_refresh': last_refresh_time.isoformat() if last_refresh_time else None,
                'refresh_count': refresh_count,
                'is_active': len(jobs) > 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get refresh status for dashboard {dashboard_id}: {e}")
            return {
                'dashboard_id': dashboard_id,
                'error': str(e),
                'is_active': False
            }
    
    def update_widget_refresh_config(self, widget_id: str, refresh_config: Dict[str, Any]):
        """Update refresh configuration for a specific widget."""
        try:
            # Store widget refresh config in Redis
            self.redis_client.setex(
                f"widget:refresh_config:{widget_id}",
                86400,  # 24 hours TTL
                json.dumps(refresh_config)
            )
            
            logger.debug(f"Updated refresh config for widget {widget_id}")
            
        except Exception as e:
            logger.error(f"Failed to update refresh config for widget {widget_id}: {e}")
    
    def get_widget_refresh_config(self, widget_id: str) -> Optional[Dict[str, Any]]:
        """Get refresh configuration for a specific widget."""
        try:
            config_data = self.redis_client.get(f"widget:refresh_config:{widget_id}")
            if config_data:
                return json.loads(config_data.decode())
            return None
            
        except Exception as e:
            logger.error(f"Failed to get refresh config for widget {widget_id}: {e}")
            return None


# Celery task for dashboard refresh
@celery_app.task(bind=True, name="dashboard.refresh_dashboard_data")
def refresh_dashboard_data(self, dashboard_id: str):
    """Celery task to refresh dashboard data."""
    try:
        logger.info(f"Starting refresh for dashboard {dashboard_id}")
        
        # Get dashboard service
        dashboard_service = DashboardService()
        widget_binding_service = WidgetDataBindingService()
        
        # Load dashboard
        dashboard = dashboard_service.get_dashboard_by_id(dashboard_id)
        if not dashboard:
            logger.error(f"Dashboard {dashboard_id} not found")
            return
        
        # Refresh each widget that has data binding
        refreshed_widgets = []
        for widget in dashboard.canvas.widgets:
            if widget.data_source:
                try:
                    # Refresh widget data
                    widget_data = widget_binding_service.refresh_widget_data(
                        widget_id=widget.id,
                        analysis_id=widget.data_source.analysis_id,
                        node_id=widget.data_source.node_id
                    )
                    
                    refreshed_widgets.append({
                        'widget_id': widget.id,
                        'status': 'success',
                        'data': widget_data
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to refresh widget {widget.id}: {e}")
                    refreshed_widgets.append({
                        'widget_id': widget.id,
                        'status': 'error',
                        'error': str(e)
                    })
        
        # Create dashboard snapshot
        from services.dashboard_snapshot_service import DashboardSnapshotService
        snapshot_service = DashboardSnapshotService()
        
        snapshot_data = {
            'dashboard_id': dashboard_id,
            'timestamp': datetime.utcnow().isoformat(),
            'widgets': refreshed_widgets,
            'trigger': 'scheduled_refresh'
        }
        
        snapshot_service.create_snapshot(dashboard_id, snapshot_data)
        
        # Update refresh count
        redis_client = redis.Redis.from_url('redis://localhost:6379/0')
        refresh_count_key = f"dashboard:refresh_count:{dashboard_id}"
        redis_client.incr(refresh_count_key)
        redis_client.expire(refresh_count_key, 86400)  # 24 hours TTL
        
        # Update last refresh time
        redis_client.setex(
            f"dashboard:last_refresh:{dashboard_id}",
            86400,
            datetime.utcnow().isoformat()
        )
        
        logger.info(f"Successfully refreshed dashboard {dashboard_id}")
        
        return {
            'status': 'success',
            'dashboard_id': dashboard_id,
            'refreshed_widgets': len(refreshed_widgets),
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to refresh dashboard {dashboard_id}: {e}")
        raise


@celery_app.task(bind=True, name="dashboard.check_analysis_and_refresh")
def check_analysis_and_refresh_dashboard(self, dashboard_id: str, analysis_ids: list):
    """Check if analyses have completed and refresh dashboard if needed."""
    try:
        analysis_service = AnalysisService()
        
        # Check if any analyses have recent runs
        should_refresh = False
        for analysis_id in analysis_ids:
            recent_runs = analysis_service.get_recent_analysis_runs(analysis_id, hours=1)
            if recent_runs:
                should_refresh = True
                break
        
        if should_refresh:
            # Trigger dashboard refresh
            refresh_dashboard_data.delay(dashboard_id)
            logger.info(f"Triggered refresh for dashboard {dashboard_id} due to analysis updates")
        
    except Exception as e:
        logger.error(f"Failed to check analysis and refresh dashboard {dashboard_id}: {e}")
        raise


# Global service instance
dashboard_refresh_service = DashboardRefreshService()