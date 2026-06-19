"""
workers/maintenance_tasks.py
Celery tasks for system maintenance, including storage quota calculations and cleanup.
"""

import os
import json
from datetime import datetime, timedelta
from celery import Celery
from logger.unified_logger import app_logger, error_logger, audit_logger
from services.storage_quota_service import storage_quota_service
from services.compliance_service import compliance_service
from services.redis_service import redis_service
from models.response import FileUpload
from mongoengine import Q
from utils.response_helper import error_response

# Initialize Celery
celery = Celery('maintenance_tasks')
celery.conf.update(
    broker_url=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    result_backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour timeout for maintenance tasks
    task_soft_time_limit=3000,  # 50 minutes soft timeout
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1,  # Restart worker after each task to free memory
)


@celery.task
def calculate_all_storage_quotas():
    """Calculate storage usage for all organizations."""
    try:
        from models.identity import Organization
        
        # Get all active organizations
        orgs = Organization.objects(status='active', is_deleted=False)
        
        processed_count = 0
        failed_count = 0
        
        for org in orgs:
            try:
                # Calculate storage usage for this organization
                storage_quota_service.calculate_storage_usage(str(org.id), force=True)
                processed_count += 1
                
                # Small delay to prevent overwhelming the database
                import time
                time.sleep(0.1)
                
            except Exception as e:
                error_logger.error(f"Error calculating storage quota for org {org.id}: {e}")
                failed_count += 1
        
        app_logger.info(f"Storage quota calculation completed: {processed_count} processed, {failed_count} failed")
        
        return {
            'status': 'completed',
            'processed': processed_count,
            'failed': failed_count,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        error_logger.error(f"Error in storage quota calculation task: {e}")
        return {
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }


@celery.task
def enforce_storage_quotas():
    """Enforce storage quotas by blocking uploads for organizations over quota."""
    try:
        from models.identity import Organization
        
        # Get all organizations
        orgs = Organization.objects(is_deleted=False)
        
        blocked_count = 0
        warning_count = 0
        
        for org in orgs:
            try:
                quota = storage_quota_service.get_organization_quota(str(org.id))
                
                # Check if organization is over quota
                if quota.used_bytes.get('total', 0) > quota.quota_bytes:
                    # Block uploads for this organization
                    _block_organization_uploads(str(org.id))
                    blocked_count += 1
                elif quota.used_bytes.get('total', 0) > quota.quota_bytes * 0.9:
                    # Send warning for organizations at 90%+ quota
                    _send_quota_warning(str(org.id), quota)
                    warning_count += 1
                
                # Small delay to prevent overwhelming the database
                import time
                time.sleep(0.1)
                
            except Exception as e:
                error_logger.error(f"Error enforcing quota for org {org.id}: {e}")
        
        app_logger.info(f"Storage quota enforcement completed: {blocked_count} blocked, {warning_count} warnings")
        
        return {
            'status': 'completed',
            'blocked': blocked_count,
            'warnings': warning_count,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        error_logger.error(f"Error in storage quota enforcement task: {e}")
        return {
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }


@celery.task
def cleanup_expired_files():
    """Clean up expired and orphaned files."""
    try:
        # Clean up files with expired retention
        cutoff_date = datetime.utcnow() - timedelta(days=30)  # 30 day retention
        
        expired_files = FileUpload.objects(
            created_at__lt=cutoff_date,
            is_deleted=False
        )
        
        deleted_count = 0
        total_size_freed = 0
        
        for file in expired_files:
            try:
                # Delete physical file
                file_path = os.path.join(os.getenv('UPLOADS_ROOT', '/var/uploads'), file.file_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    total_size_freed += file.file_size_bytes or 0
                
                # Update database record
                file.is_deleted = True
                file.deleted_at = datetime.utcnow()
                file.save()
                
                # Update storage quota
                storage_quota_service.record_file_deletion(file.org_id, file.file_size_bytes or 0)
                
                deleted_count += 1
                
            except Exception as e:
                error_logger.error(f"Error deleting file {file.id}: {e}")
        
        app_logger.info(f"File cleanup completed: {deleted_count} files deleted, {total_size_freed} bytes freed")
        
        return {
            'status': 'completed',
            'deleted_files': deleted_count,
            'bytes_freed': total_size_freed,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        error_logger.error(f"Error in file cleanup task: {e}")
        return {
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }


@celery.task
def enforce_retention_policies():
    """Enforce data retention policies for compliant organizations."""
    try:
        from models.identity import Organization
        
        # Get organizations with compliance standards
        orgs = Organization.objects(compliance_ids__ne=[], is_deleted=False)
        
        processed_count = 0
        failed_count = 0
        
        for org in orgs:
            try:
                # Enforce retention policies for each compliance standard
                for compliance_id in org.compliance_ids:
                    compliance_service.enforce_retention_policy(compliance_id, str(org.id))
                
                processed_count += 1
                
                # Small delay to prevent overwhelming the database
                import time
                time.sleep(0.1)
                
            except Exception as e:
                error_logger.error(f"Error enforcing retention policies for org {org.id}: {e}")
                failed_count += 1
        
        app_logger.info(f"Retention policy enforcement completed: {processed_count} processed, {failed_count} failed")
        
        return {
            'status': 'completed',
            'processed': processed_count,
            'failed': failed_count,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        error_logger.error(f"Error in retention policy enforcement task: {e}")
        return {
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }


@celery.task
def cleanup_old_audit_logs():
    """Archive old audit logs to maintain performance."""
    try:
        from models.oauth import AuditLog
        
        # Archive logs older than 90 days
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        old_logs = AuditLog.objects(timestamp__lt=cutoff_date, archived=False)
        
        archived_count = 0
        
        for log in old_logs:
            try:
                # Mark as archived instead of deleting
                log.archived = True
                log.save()
                archived_count += 1
                
            except Exception as e:
                error_logger.error(f"Error archiving audit log {log.id}: {e}")
        
        app_logger.info(f"Audit log archiving completed: {archived_count} logs archived")
        
        return {
            'status': 'completed',
            'archived_logs': archived_count,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        error_logger.error(f"Error in audit log cleanup task: {e}")
        return {
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }


@celery.task
def generate_usage_reports():
    """Generate daily usage reports for administrators."""
    try:
        from models.identity import Organization
        
        # Get all organizations
        orgs = Organization.objects(is_deleted=False)
        
        reports = []
        
        for org in orgs:
            try:
                # Get storage quota statistics
                quota_stats = storage_quota_service.get_quota_statistics(str(org.id))
                
                # Get organization statistics
                org_stats = {
                    'org_id': str(org.id),
                    'org_name': org.name,
                    'created_at': org.created_at.isoformat(),
                    'status': org.status,
                    'storage_quota': quota_stats,
                    'member_count': org.members.count() if hasattr(org, 'members') else 0,
                    'project_count': org.projects.count() if hasattr(org, 'projects') else 0,
                    'form_count': org.forms.count() if hasattr(org, 'forms') else 0
                }
                
                reports.append(org_stats)
                
                # Small delay to prevent overwhelming the database
                import time
                time.sleep(0.1)
                
            except Exception as e:
                error_logger.error(f"Error generating report for org {org.id}: {e}")
        
        # Store report in Redis for 24 hours
        redis = redis_service().cache
        report_key = f"daily_usage_report:{datetime.utcnow().strftime('%Y-%m-%d')}"
        redis.setex(report_key, 86400, json.dumps(reports))
        
        app_logger.info(f"Daily usage report generated: {len(reports)} organizations")
        
        return {
            'status': 'completed',
            'organizations': len(reports),
            'report_key': report_key,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        error_logger.error(f"Error in usage report generation task: {e}")
        return {
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }


def _block_organization_uploads(org_id):
    """Block file uploads for an organization over quota."""
    try:
        # Set flag in Redis to block uploads
        redis = redis_service().cache
        block_key = f"upload_blocked:{org_id}"
        redis.setex(block_key, 3600, "quota_exceeded")  # Block for 1 hour
        
        # Log the blocking
        audit_logger.info(f"File uploads blocked for organization {org_id} due to quota exceeded")
        
    except Exception as e:
        error_logger.error(f"Error blocking uploads for org {org_id}: {e}")


def _send_quota_warning(org_id, quota):
    """Send quota warning notification."""
    try:
        # Check if we've already sent a warning recently
        redis = redis_service().cache
        warning_key = f"quota_warning:{org_id}:{datetime.utcnow().strftime('%Y-%m-%d')}"
        
        if redis.get(warning_key):
            return  # Already sent warning today
        
        # Send warning (this would integrate with your notification system)
        # For now, just log it
        usage_ratio = quota.used_bytes.get('total', 0) / quota.quota_bytes if quota.quota_bytes else 0
        
        audit_logger.warning(
            f"Organization {org_id} is at {usage_ratio:.1%} storage quota "
            f"({quota.used_bytes.get('total', 0)} / {quota.quota_bytes} bytes)"
        )
        
        # Set warning flag for 24 hours
        redis.setex(warning_key, 86400, "1")
        
    except Exception as e:
        error_logger.error(f"Error sending quota warning for org {org_id}: {e}")


# Schedule periodic tasks
celery.conf.beat_schedule = {
    'calculate-storage-quotas': {
        'task': 'workers.maintenance_tasks.calculate_all_storage_quotas',
        'schedule': 3600.0,  # Every hour
    },
    'enforce-storage-quotas': {
        'task': 'workers.maintenance_tasks.enforce_storage_quotas',
        'schedule': 1800.0,  # Every 30 minutes
    },
    'cleanup-expired-files': {
        'task': 'workers.maintenance_tasks.cleanup_expired_files',
        'schedule': 86400.0,  # Every day
    },
    'enforce-retention-policies': {
        'task': 'workers.maintenance_tasks.enforce_retention_policies',
        'schedule': 43200.0,  # Every 12 hours
    },
    'cleanup-old-audit-logs': {
        'task': 'workers.maintenance_tasks.cleanup_old_audit_logs',
        'schedule': 86400.0,  # Every day
    },
    'generate-usage-reports': {
        'task': 'workers.maintenance_tasks.generate_usage_reports',
        'schedule': 86400.0,  # Every day at midnight
    },
}