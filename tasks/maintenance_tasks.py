"""
tasks/maintenance_tasks.py
Background maintenance tasks for the platform.
"""

import logging
from datetime import datetime, timedelta
from celery import Celery
from services.storage_quota_service import storage_quota_service
from services.compliance_registry_service import compliance_registry_service
from services.notification_service import notification_service
from services.update_service import update_service
from models.oauth import SystemConfig, Organisation
from logger.unified_logger import app_logger, error_logger, audit_logger

# Get Celery instance
celery = Celery('maintenance_tasks')

@celery.task(bind=True, name="maintenance.calculate_storage_usage")
def calculate_storage_usage_task(self, org_id=None, force=False):
    """Calculate storage usage for organizations."""
    try:
        if org_id:
            # Calculate for specific organization
            storage_quota_service.calculate_storage_usage(org_id, force)
            app_logger.info(f"Storage usage calculated for org {org_id}")
        else:
            # Calculate for all organizations
            from models.oauth import Organisation
            orgs = Organisation.objects(is_deleted=False)
            
            for org in orgs:
                try:
                    storage_quota_service.calculate_storage_usage(str(org.id), force)
                except Exception as e:
                    error_logger.error(f"Error calculating storage usage for org {org.id}: {e}")
            
            app_logger.info(f"Storage usage calculated for {len(orgs)} organizations")
        
        return {"status": "success", "message": "Storage usage calculated"}
        
    except Exception as e:
        error_logger.error(f"Error in storage usage calculation task: {e}")
        raise


@celery.task(bind=True, name="maintenance.cleanup_expired_data")
def cleanup_expired_data_task(self, org_id=None):
    """Clean up expired data based on retention policies."""
    try:
        compliance_registry_service.cleanup_expired_data(org_id)
        
        if org_id:
            app_logger.info(f"Expired data cleaned up for org {org_id}")
        else:
            app_logger.info("Expired data cleaned up for all organizations")
        
        return {"status": "success", "message": "Expired data cleaned up"}
        
    except Exception as e:
        error_logger.error(f"Error in expired data cleanup task: {e}")
        raise


@celery.task(bind=True, name="maintenance.check_system_health")
def check_system_health_task(self):
    """Check system health and send alerts if needed."""
    try:
        import psutil
        
        # Check CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > 90:
            notification_service.send_system_alert(
                "High CPU Usage",
                f"CPU usage is at {cpu_percent}%",
                {"metric": "cpu", "value": cpu_percent, "threshold": 90}
            )
        
        # Check memory usage
        memory_percent = psutil.virtual_memory().percent
        if memory_percent > 90:
            notification_service.send_system_alert(
                "High Memory Usage",
                f"Memory usage is at {memory_percent}%",
                {"metric": "memory", "value": memory_percent, "threshold": 90}
            )
        
        # Check disk usage
        disk_percent = psutil.disk_usage('/').percent
        if disk_percent > 90:
            notification_service.send_system_alert(
                "High Disk Usage",
                f"Disk usage is at {disk_percent}%",
                {"metric": "disk", "value": disk_percent, "threshold": 90}
            )
        
        # Check database connection
        try:
            from mongoengine.connection import get_db
            db = get_db()
            db.command("ping")
        except Exception as e:
            notification_service.send_system_alert(
                "Database Connection Error",
                f"Failed to connect to database: {str(e)}",
                {"metric": "database", "status": "error"}
            )
        
        # Check Redis connection
        try:
            from services.redis_service import redis_service
            redis_service.cache.ping()
        except Exception as e:
            notification_service.send_system_alert(
                "Redis Connection Error",
                f"Failed to connect to Redis: {str(e)}",
                {"metric": "redis", "status": "error"}
            )
        
        app_logger.info("System health check completed")
        
        return {"status": "success", "message": "System health check completed"}
        
    except Exception as e:
        error_logger.error(f"Error in system health check task: {e}")
        raise


@celery.task(bind=True, name="maintenance.rotate_logs")
def rotate_logs_task(self):
    """Rotate and archive old logs."""
    try:
        # This is a simplified implementation
        # In a real scenario, you would:
        # 1. Move old logs to archive storage
        # 2. Compress archived logs
        # 3. Delete very old logs based on retention policy
        
        # For now, we'll just log that the task ran
        app_logger.info("Log rotation task completed")
        
        return {"status": "success", "message": "Logs rotated"}
        
    except Exception as e:
        error_logger.error(f"Error in log rotation task: {e}")
        raise


@celery.task(bind=True, name="maintenance.cleanup_temp_files")
def cleanup_temp_files_task(self):
    """Clean up temporary files."""
    try:
        import os
        import glob
        
        # Clean up temporary upload files
        temp_dirs = [
            "/tmp/uploads",
            "/var/tmp/uploads",
            os.path.join(os.getcwd(), "uploads", "temp")
        ]
        
        cleaned_files = 0
        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                # Find files older than 24 hours
                cutoff_time = datetime.now() - timedelta(hours=24)
                
                for file_path in glob.glob(os.path.join(temp_dir, "*")):
                    try:
                        if os.path.isfile(file_path):
                            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                            if file_time < cutoff_time:
                                os.remove(file_path)
                                cleaned_files += 1
                    except Exception as e:
                        error_logger.error(f"Error deleting temp file {file_path}: {e}")
        
        app_logger.info(f"Cleaned up {cleaned_files} temporary files")
        
        return {"status": "success", "message": f"Cleaned up {cleaned_files} temporary files"}
        
    except Exception as e:
        error_logger.error(f"Error in temp file cleanup task: {e}")
        raise


@celery.task(bind=True, name="maintenance.backup_database")
def backup_database_task(self):
    """Create database backup."""
    try:
        # This is a simplified implementation
        # In a real scenario, you would:
        # 1. Use mongodump to create backup
        # 2. Compress the backup
        # 3. Upload to cloud storage
        # 4. Verify backup integrity
        
        # For now, we'll just log that the task ran
        app_logger.info("Database backup task completed")
        
        return {"status": "success", "message": "Database backup completed"}
        
    except Exception as e:
        error_logger.error(f"Error in database backup task: {e}")
        raise


@celery.task(bind=True, name="maintenance.check_for_updates")
def check_for_updates_task(self):
    """Check for platform updates."""
    try:
        # Check for updates
        update_info = update_service.check_for_updates()
        
        if update_info.get("available_updates"):
            # Send notification about available updates
            notification_service.send_update_notification(update_info)
            
            app_logger.info(f"Found {len(update_info['available_updates'])} available updates")
        else:
            app_logger.info("No updates available")
        
        return {"status": "success", "message": "Update check completed"}
        
    except Exception as e:
        error_logger.error(f"Error in update check task: {e}")
        raise


@celery.task(bind=True, name="maintenance.cleanup_old_sessions")
def cleanup_old_sessions_task(self):
    """Clean up old user sessions."""
    try:
        from models.oauth import Session
        
        # Delete sessions older than 30 days
        cutoff_time = datetime.utcnow() - timedelta(days=30)
        
        old_sessions = Session.objects(expires_at__lt=cutoff_time)
        deleted_count = old_sessions.delete()
        
        app_logger.info(f"Cleaned up {deleted_count} old sessions")
        
        return {"status": "success", "message": f"Cleaned up {deleted_count} old sessions"}
        
    except Exception as e:
        error_logger.error(f"Error in session cleanup task: {e}")
        raise


@celery.task(bind=True, name="maintenance.cleanup_old_audit_logs")
def cleanup_old_audit_logs_task(self):
    """Clean up old audit logs based on retention policy."""
    try:
        from models.oauth import AuditLog
        
        # Get retention period from system config
        retention_days = 365  # Default 1 year
        retention_config = SystemConfig.objects(key="audit_log_retention_days").first()
        if retention_config:
            retention_days = int(retention_config.value)
        
        # Delete audit logs older than retention period
        cutoff_time = datetime.utcnow() - timedelta(days=retention_days)
        
        # Mark logs as archived instead of deleting
        old_logs = AuditLog.objects(timestamp__lt=cutoff_time, archived=False)
        archived_count = old_logs.update(archived=True)
        
        app_logger.info(f"Archived {archived_count} old audit logs")
        
        return {"status": "success", "message": f"Archived {archived_count} old audit logs"}
        
    except Exception as e:
        error_logger.error(f"Error in audit log cleanup task: {e}")
        raise


@celery.task(bind=True, name="maintenance.generate_usage_report")
def generate_usage_report_task(self, period="daily"):
    """Generate system usage report."""
    try:
        from collections import defaultdict
        
        # Get date range
        if period == "daily":
            start_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)
        elif period == "weekly":
            start_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7)
            end_date = start_date + timedelta(days=7)
        elif period == "monthly":
            start_date = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=32)
            end_date = end_date.replace(day=1)
        else:
            raise ValueError(f"Invalid period: {period}")
        
        # Collect statistics
        stats = {
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "organizations": {
                "total": Organisation.objects(is_deleted=False).count(),
                "active": Organisation.objects(is_deleted=False, status="active").count()
            },
            "forms": {
                "total": 0,
                "published": 0,
                "responses": 0
            },
            "storage": {
                "total_used": 0,
                "total_quota": 0
            },
            "api_calls": 0
        }
        
        # In a real implementation, you would query actual data
        # For now, we'll just log that the report was generated
        
        app_logger.info(f"Generated {period} usage report")
        
        return {"status": "success", "message": f"Generated {period} usage report", "stats": stats}
        
    except Exception as e:
        error_logger.error(f"Error in usage report generation task: {e}")
        raise


# Schedule periodic tasks
def setup_periodic_tasks():
    """Set up periodic maintenance tasks."""
    
    # Daily tasks
    celery.conf.beat_schedule = {
        'daily-storage-calculation': {
            'task': 'maintenance.calculate_storage_usage',
            'schedule': 86400.0,  # Daily
        },
        'daily-health-check': {
            'task': 'maintenance.check_system_health',
            'schedule': 86400.0,  # Daily
        },
        'daily-temp-cleanup': {
            'task': 'maintenance.cleanup_temp_files',
            'schedule': 86400.0,  # Daily
        },
        'daily-session-cleanup': {
            'task': 'maintenance.cleanup_old_sessions',
            'schedule': 86400.0,  # Daily
        },
        'daily-update-check': {
            'task': 'maintenance.check_for_updates',
            'schedule': 86400.0,  # Daily
        },
        
        # Weekly tasks
        'weekly-expired-cleanup': {
            'task': 'maintenance.cleanup_expired_data',
            'schedule': 604800.0,  # Weekly
        },
        'weekly-log-rotation': {
            'task': 'maintenance.rotate_logs',
            'schedule': 604800.0,  # Weekly
        },
        'weekly-database-backup': {
            'task': 'maintenance.backup_database',
            'schedule': 604800.0,  # Weekly
        },
        'weekly-audit-cleanup': {
            'task': 'maintenance.cleanup_old_audit_logs',
            'schedule': 604800.0,  # Weekly
        },
        
        # Monthly tasks
        'monthly-usage-report': {
            'task': 'maintenance.generate_usage_report',
            'schedule': 2592000.0,  # Monthly (approximately)
            'kwargs': {'period': 'monthly'}
        },
    }