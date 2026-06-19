"""
services/storage_quota_service.py
Storage quota management service for organizations.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from models.identity import Organization, StorageQuota
from models.response import FileUpload
from mongoengine import Q
from logger.unified_logger import app_logger, error_logger, audit_logger
from services.notification_service import notification_service
from services.redis_service import redis_service

class StorageQuotaService:
    """Service for managing storage quotas and usage tracking."""
    
    def __init__(self):
        self.redis = redis_service().cache
        self.default_quota_bytes = 10 * 1024 * 1024 * 1024  # 10 GB default
        self.warning_thresholds = [0.8, 0.9, 1.0]  # 80%, 90%, 100%
        self.quota_cache_key = "storage_quota:{org_id}"
        self.quota_cache_ttl = 3600  # 1 hour
    
    def get_organization_quota(self, org_id: str) -> StorageQuota:
        """Get or create storage quota for an organization."""
        # Try to get from cache first
        cache_key = self.quota_cache_key.format(org_id=org_id)
        cached_quota = self.redis.get(cache_key)
        
        if cached_quota:
            from bson import json_util
            import json
            quota_data = json.loads(cached_quota)
            return StorageQuota._from_son(quota_data)
        
        # Get from database
        quota = StorageQuota.objects(org_id=org_id).first()
        
        if not quota:
            # Create default quota
            quota = StorageQuota(
                org_id=org_id,
                quota_bytes=self.default_quota_bytes,
                used_bytes={
                    "files": 0,
                    "database": 0,
                    "audit_logs": 0,
                    "total": 0
                },
                warning_threshold=0.8,
                last_calculated_at=datetime.utcnow()
            )
            quota.save()
        
        # Cache the quota
        self._cache_quota(quota)
        
        return quota
    
    def _cache_quota(self, quota: StorageQuota):
        """Cache quota data in Redis."""
        cache_key = self.quota_cache_key.format(org_id=quota.org_id)
        quota_data = quota.to_mongo().to_dict()
        
        import json
        from bson import json_util
        cached_data = json_util.dumps(quota_data)
        
        self.redis.setex(cache_key, self.quota_cache_ttl, cached_data)
    
    def update_quota(self, org_id: str, quota_bytes: int, set_by: str = None):
        """Update organization's storage quota."""
        quota = self.get_organization_quota(org_id)
        
        old_quota = quota.quota_bytes
        quota.quota_bytes = quota_bytes
        quota.set_by = set_by
        quota.updated_at = datetime.utcnow()
        quota.save()
        
        # Update cache
        self._cache_quota(quota)
        
        # Log the change
        audit_logger.info(f"Storage quota updated for org {org_id}: {old_quota} -> {quota_bytes} bytes by {set_by}")
        
        # Send notification
        if set_by:
            notification_service.send_quota_updated_notification(
                org_id=org_id,
                old_quota=old_quota,
                new_quota=quota_bytes
            )
        
        return quota
    
    def calculate_storage_usage(self, org_id: str, force: bool = False) -> Dict:
        """Calculate actual storage usage for an organization."""
        quota = self.get_organization_quota(org_id)
        
        # Check if we need to recalculate
        if not force and quota.last_calculated_at:
            time_since_last = datetime.utcnow() - quota.last_calculated_at
            if time_since_last.total_seconds() < 3600:  # Less than 1 hour
                return quota.used_bytes
        
        try:
            # Calculate file storage usage
            files_usage = self._calculate_files_usage(org_id)
            
            # Estimate database usage
            db_usage = self._estimate_database_usage(org_id)
            
            # Estimate audit logs usage
            audit_usage = self._estimate_audit_logs_usage(org_id)
            
            # Update quota
            total_usage = files_usage + db_usage + audit_usage
            quota.used_bytes = {
                "files": files_usage,
                "database": db_usage,
                "audit_logs": audit_usage,
                "total": total_usage
            }
            quota.last_calculated_at = datetime.utcnow()
            quota.save()
            
            # Update cache
            self._cache_quota(quota)
            
            # Check for quota warnings
            self._check_quota_warnings(quota)
            
            return quota.used_bytes
            
        except Exception as e:
            error_logger.error(f"Error calculating storage usage for org {org_id}: {e}")
            return quota.used_bytes
    
    def _calculate_files_usage(self, org_id: str) -> int:
        """Calculate total file storage usage."""
        total_size = 0
        
        try:
            # Get all file uploads for the organization
            files = FileUpload.objects(
                org_id=org_id,
                is_deleted=False,
                upload_status="complete"
            ).only('file_size_bytes')
            
            for file in files:
                total_size += file.file_size_bytes or 0
            
            return total_size
            
        except Exception as e:
            error_logger.error(f"Error calculating files usage for org {org_id}: {e}")
            return 0
    
    def _estimate_database_usage(self, org_id: str) -> int:
        """Estimate database storage usage for organization data."""
        # This is a simplified estimation
        # In a real implementation, you might use MongoDB's dbStats command
        
        try:
            # Count documents in key collections
            from models.identity import User, Organization
            from models.form_models import Project, Form, FormResponse
            
            collections = [
                (User, "users"),
                (Organization, "organizations"),
                (Project, "projects"),
                (Form, "forms"),
                (FormResponse, "form_responses")
            ]
            
            total_docs = 0
            for model, name in collections:
                count = model.objects(org_id=org_id, is_deleted=False).count()
                total_docs += count
            
            # Estimate average document size (rough estimate)
            avg_doc_size = 2048  # 2KB average
            db_usage = total_docs * avg_doc_size
            
            return db_usage
            
        except Exception as e:
            error_logger.error(f"Error estimating database usage for org {org_id}: {e}")
            return 0
    
    def _estimate_audit_logs_usage(self, org_id: str) -> int:
        """Estimate audit logs storage usage."""
        try:
            from models.oauth import AuditLog
            
            # Count audit logs for the organization
            log_count = AuditLog.objects(org_id=org_id).count()
            
            # Estimate average log size
            avg_log_size = 512  # 512 bytes average
            audit_usage = log_count * avg_log_size
            
            return audit_usage
            
        except Exception as e:
            error_logger.error(f"Error estimating audit logs usage for org {org_id}: {e}")
            return 0
    
    def _check_quota_warnings(self, quota: StorageQuota):
        """Check for quota warnings and send notifications."""
        if not quota.quota_bytes:
            return
        
        usage_ratio = quota.used_bytes.get("total", 0) / quota.quota_bytes
        
        for threshold in self.warning_thresholds:
            if abs(usage_ratio - threshold) < 0.01:  # Within 1% of threshold
                self._send_quota_warning(quota, threshold, usage_ratio)
                break
    
    def _send_quota_warning(self, quota: StorageQuota, threshold: float, usage_ratio: float):
        """Send quota warning notification."""
        try:
            # Check if we've already sent this warning recently
            warning_key = f"quota_warning:{quota.org_id}:{threshold}"
            if self.redis.get(warning_key):
                return
            
            # Send notification
            notification_service.send_quota_warning_notification(
                org_id=quota.org_id,
                threshold=threshold,
                usage_ratio=usage_ratio,
                used_bytes=quota.used_bytes.get("total", 0),
                quota_bytes=quota.quota_bytes
            )
            
            # Set warning flag for 24 hours
            self.redis.setex(warning_key, 86400, "1")
            
        except Exception as e:
            error_logger.error(f"Error sending quota warning for org {quota.org_id}: {e}")
    
    def check_file_upload_allowed(self, org_id: str, file_size: int) -> bool:
        """Check if file upload is allowed based on quota."""
        quota = self.get_organization_quota(org_id)
        
        # If quota is exceeded, block uploads
        if quota.used_bytes.get("total", 0) >= quota.quota_bytes:
            return False
        
        # Check if adding this file would exceed quota
        new_total = quota.used_bytes.get("total", 0) + file_size
        if new_total > quota.quota_bytes:
            return False
        
        return True
    
    def record_file_upload(self, org_id: str, file_size: int):
        """Record a file upload and update usage."""
        try:
            quota = self.get_organization_quota(org_id)
            quota.used_bytes["files"] += file_size
            quota.used_bytes["total"] += file_size
            quota.updated_at = datetime.utcnow()
            quota.save()
            
            # Update cache
            self._cache_quota(quota)
            
            # Check for warnings
            self._check_quota_warnings(quota)
            
        except Exception as e:
            error_logger.error(f"Error recording file upload for org {org_id}: {e}")
    
    def record_file_deletion(self, org_id: str, file_size: int):
        """Record a file deletion and update usage."""
        try:
            quota = self.get_organization_quota(org_id)
            quota.used_bytes["files"] = max(0, quota.used_bytes["files"] - file_size)
            quota.used_bytes["total"] = max(0, quota.used_bytes["total"] - file_size)
            quota.updated_at = datetime.utcnow()
            quota.save()
            
            # Update cache
            self._cache_quota(quota)
            
        except Exception as e:
            error_logger.error(f"Error recording file deletion for org {org_id}: {e}")
    
    def get_quota_statistics(self, org_id: str = None) -> Dict:
        """Get storage quota statistics."""
        if org_id:
            quota = self.get_organization_quota(org_id)
            return {
                "org_id": org_id,
                "quota_bytes": quota.quota_bytes,
                "used_bytes": quota.used_bytes,
                "usage_ratio": quota.used_bytes.get("total", 0) / quota.quota_bytes if quota.quota_bytes else 0,
                "available_bytes": quota.quota_bytes - quota.used_bytes.get("total", 0) if quota.quota_bytes else 0,
                "last_calculated_at": quota.last_calculated_at.isoformat() if quota.last_calculated_at else None
            }
        else:
            # Get all organizations' quota statistics
            quotas = StorageQuota.objects()
            stats = []
            
            for quota in quotas:
                stats.append({
                    "org_id": quota.org_id,
                    "quota_bytes": quota.quota_bytes,
                    "used_bytes": quota.used_bytes,
                    "usage_ratio": quota.used_bytes.get("total", 0) / quota.quota_bytes if quota.quota_bytes else 0,
                    "available_bytes": quota.quota_bytes - quota.used_bytes.get("total", 0) if quota.quota_bytes else 0,
                    "last_calculated_at": quota.last_calculated_at.isoformat() if quota.last_calculated_at else None
                })
            
            return {
                "total_organizations": len(stats),
                "organizations": stats
            }
    
    def cleanup_expired_data(self, org_id: str = None):
        """Clean up expired data based on retention policies."""
        try:
            from services.compliance_registry_service import compliance_registry_service
            
            if org_id:
                # Clean up for specific organization
                org = Organization.objects(id=org_id).first()
                if org and org.compliance_ids:
                    for compliance_id in org.compliance_ids:
                        compliance_registry_service.enforce_retention_policy(compliance_id, org_id)
            else:
                # Clean up for all organizations
                orgs = Organization.objects(compliance_ids__ne=[])
                for org in orgs:
                    for compliance_id in org.compliance_ids:
                        compliance_registry_service.enforce_retention_policy(compliance_id, str(org.id))
            
        except Exception as e:
            error_logger.error(f"Error cleaning up expired data: {e}")

# Global storage quota service instance
storage_quota_service = StorageQuotaService()