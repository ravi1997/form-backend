"""
services/llm_usage_tracking_service.py
Service for tracking LLM usage and costs.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import uuid

from logger.unified_logger import app_logger, error_logger
from models.llm_model import LLMUsage, LLMOrganizationQuota
from utils.exceptions import NotFoundError, ValidationError


class UsagePeriod(Enum):
    """Usage aggregation periods."""
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class LLMUsageTrackingService:
    """Service for tracking LLM usage and managing quotas."""

    def __init__(self):
        self._quota_cache = {}  # Cache for organization quotas

    async def track_usage(
        self,
        user_id: str,
        organization_id: str,
        provider: str,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
        request_id: str = None,
        session_id: str = None,
        metadata: Dict[str, Any] = None
    ) -> LLMUsage:
        """Track LLM usage and update quotas."""
        try:
            app_logger.info(f"Tracking LLM usage for user {user_id}, org {organization_id}")
            
            # Create usage record
            usage = LLMUsage(
                user_id=user_id,
                organization_id=organization_id,
                provider=provider,
                model_id=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                cost=cost,
                request_id=request_id or str(uuid.uuid4()),
                session_id=session_id,
                metadata=metadata or {}
            )
            usage.save()
            
            # Update organization quota
            await self._update_organization_quota(organization_id, cost)
            
            app_logger.info(f"Successfully tracked LLM usage: {usage.id}")
            return usage
            
        except Exception as e:
            error_logger.error(f"Failed to track LLM usage: {str(e)}", exc_info=True)
            raise

    async def get_user_usage(
        self,
        user_id: str,
        organization_id: str = None,
        period: str = "month"
    ) -> Dict[str, Any]:
        """Get usage statistics for a user."""
        try:
            # Calculate date range based on period
            end_date = datetime.utcnow()
            if period == UsagePeriod.DAY.value:
                start_date = end_date - timedelta(days=1)
            elif period == UsagePeriod.WEEK.value:
                start_date = end_date - timedelta(weeks=1)
            elif period == UsagePeriod.MONTH.value:
                start_date = end_date - timedelta(days=30)
            elif period == UsagePeriod.YEAR.value:
                start_date = end_date - timedelta(days=365)
            else:
                raise ValidationError(f"Invalid period: {period}")
            
            # Query usage records
            query = LLMUsage.objects(
                user_id=user_id,
                timestamp__gte=start_date,
                timestamp__lte=end_date
            )
            
            if organization_id:
                query = query.filter(organization_id=organization_id)
            
            usage_records = query.order_by("-timestamp")
            
            # Calculate statistics
            total_tokens = sum(record.total_tokens for record in usage_records)
            total_cost = sum(record.cost for record in usage_records)
            total_requests = len(usage_records)
            
            # Group by provider
            provider_stats = {}
            for record in usage_records:
                provider = record.provider
                if provider not in provider_stats:
                    provider_stats[provider] = {
                        "tokens": 0,
                        "cost": 0.0,
                        "requests": 0
                    }
                
                provider_stats[provider]["tokens"] += record.total_tokens
                provider_stats[provider]["cost"] += record.cost
                provider_stats[provider]["requests"] += 1
            
            # Group by model
            model_stats = {}
            for record in usage_records:
                model = record.model_id
                if model not in model_stats:
                    model_stats[model] = {
                        "tokens": 0,
                        "cost": 0.0,
                        "requests": 0
                    }
                
                model_stats[model]["tokens"] += record.total_tokens
                model_stats[model]["cost"] += record.cost
                model_stats[model]["requests"] += 1
            
            # Get organization quota if applicable
            quota_info = None
            if organization_id:
                quota_info = await self.get_organization_quota(organization_id)
            
            return {
                "period": period,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_tokens": total_tokens,
                "total_cost": total_cost,
                "total_requests": total_requests,
                "provider_breakdown": provider_stats,
                "model_breakdown": model_stats,
                "quota": quota_info
            }
            
        except Exception as e:
            error_logger.error(f"Failed to get user usage: {str(e)}", exc_info=True)
            raise

    async def get_organization_usage(
        self,
        organization_id: str,
        period: str = "month"
    ) -> Dict[str, Any]:
        """Get usage statistics for an organization."""
        try:
            # Calculate date range based on period
            end_date = datetime.utcnow()
            if period == UsagePeriod.DAY.value:
                start_date = end_date - timedelta(days=1)
            elif period == UsagePeriod.WEEK.value:
                start_date = end_date - timedelta(weeks=1)
            elif period == UsagePeriod.MONTH.value:
                start_date = end_date - timedelta(days=30)
            elif period == UsagePeriod.YEAR.value:
                start_date = end_date - timedelta(days=365)
            else:
                raise ValidationError(f"Invalid period: {period}")
            
            # Query usage records
            usage_records = LLMUsage.objects(
                organization_id=organization_id,
                timestamp__gte=start_date,
                timestamp__lte=end_date
            ).order_by("-timestamp")
            
            # Calculate statistics
            total_tokens = sum(record.total_tokens for record in usage_records)
            total_cost = sum(record.cost for record in usage_records)
            total_requests = len(usage_records)
            
            # Group by user
            user_stats = {}
            for record in usage_records:
                user_id = str(record.user_id)
                if user_id not in user_stats:
                    user_stats[user_id] = {
                        "tokens": 0,
                        "cost": 0.0,
                        "requests": 0
                    }
                
                user_stats[user_id]["tokens"] += record.total_tokens
                user_stats[user_id]["cost"] += record.cost
                user_stats[user_id]["requests"] += 1
            
            # Get quota information
            quota_info = await self.get_organization_quota(organization_id)
            
            return {
                "period": period,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_tokens": total_tokens,
                "total_cost": total_cost,
                "total_requests": total_requests,
                "user_breakdown": user_stats,
                "quota": quota_info
            }
            
        except Exception as e:
            error_logger.error(f"Failed to get organization usage: {str(e)}", exc_info=True)
            raise

    async def get_organization_quota(self, organization_id: str) -> Dict[str, Any]:
        """Get organization quota information."""
        try:
            # Check cache first
            if organization_id in self._quota_cache:
                cache_entry = self._quota_cache[organization_id]
                # Cache expires after 5 minutes
                if (datetime.utcnow() - cache_entry["timestamp"]).total_seconds() < 300:
                    return cache_entry["quota"]
            
            # Get quota from database
            quota = LLMOrganizationQuota.objects(
                organization_id=organization_id
            ).first()
            
            if not quota:
                # Create default quota
                quota = LLMOrganizationQuota(
                    organization_id=organization_id,
                    monthly_limit=100.0,  # $100 default monthly limit
                    warning_threshold=80.0,
                    period_type="monthly",
                    current_usage=0.0
                )
                quota.save()
            
            # Calculate usage percentage
            usage_percentage = (quota.current_usage / quota.monthly_limit) * 100 if quota.monthly_limit > 0 else 0
            
            quota_info = {
                "organization_id": str(quota.organization_id),
                "monthly_limit": quota.monthly_limit,
                "current_usage": quota.current_usage,
                "remaining_quota": quota.monthly_limit - quota.current_usage,
                "usage_percentage": usage_percentage,
                "warning_threshold": quota.warning_threshold,
                "period_type": quota.period_type,
                "last_reset_at": quota.last_reset_at.isoformat(),
                "is_warning_threshold_exceeded": usage_percentage >= quota.warning_threshold,
                "is_quota_exceeded": usage_percentage >= 100.0
            }
            
            # Cache result
            self._quota_cache[organization_id] = {
                "quota": quota_info,
                "timestamp": datetime.utcnow()
            }
            
            return quota_info
            
        except Exception as e:
            error_logger.error(f"Failed to get organization quota: {str(e)}", exc_info=True)
            raise

    async def set_organization_quota(
        self,
        organization_id: str,
        monthly_limit: float,
        warning_threshold: float = 80.0
    ) -> Dict[str, Any]:
        """Set organization quota."""
        try:
            app_logger.info(f"Setting quota for organization {organization_id}: ${monthly_limit}")
            
            # Get or create quota
            quota = LLMOrganizationQuota.objects(
                organization_id=organization_id
            ).first()
            
            if quota:
                quota.monthly_limit = monthly_limit
                quota.warning_threshold = warning_threshold
                quota.updated_by = "system"  # Should be passed as parameter
                quota.updated_at = datetime.utcnow()
                quota.save()
            else:
                quota = LLMOrganizationQuota(
                    organization_id=organization_id,
                    monthly_limit=monthly_limit,
                    warning_threshold=warning_threshold,
                    period_type="monthly",
                    current_usage=0.0,
                    created_by="system"  # Should be passed as parameter
                )
                quota.save()
            
            # Clear cache
            if organization_id in self._quota_cache:
                del self._quota_cache[organization_id]
            
            audit_logger.info(
                f"AUDIT: Organization quota updated: {organization_id}, limit: ${monthly_limit}"
            )
            
            return await self.get_organization_quota(organization_id)
            
        except Exception as e:
            error_logger.error(f"Failed to set organization quota: {str(e)}", exc_info=True)
            raise

    async def _update_organization_quota(self, organization_id: str, cost: float):
        """Update organization quota usage."""
        try:
            quota = LLMOrganizationQuota.objects(
                organization_id=organization_id
            ).first()
            
            if quota:
                # Check if we need to reset the quota (new month)
                now = datetime.utcnow()
                if quota.last_reset_at:
                    # Reset if we're in a new month
                    if (now.year > quota.last_reset_at.year or 
                        now.month > quota.last_reset_at.month):
                        quota.current_usage = 0.0
                        quota.last_reset_at = now
                
                # Add cost to current usage
                quota.current_usage += cost
                quota.updated_at = now
                quota.save()
                
                # Clear cache
                if organization_id in self._quota_cache:
                    del self._quota_cache[organization_id]
                
                # Check if quota is exceeded
                usage_percentage = (quota.current_usage / quota.monthly_limit) * 100 if quota.monthly_limit > 0 else 0
                if usage_percentage >= 100.0:
                    app_logger.warning(
                        f"Organization {organization_id} has exceeded LLM quota: {usage_percentage:.1f}%"
                    )
                elif usage_percentage >= quota.warning_threshold:
                    app_logger.warning(
                        f"Organization {organization_id} has exceeded warning threshold: {usage_percentage:.1f}%"
                    )
            
        except Exception as e:
            error_logger.error(f"Failed to update organization quota: {str(e)}", exc_info=True)
            # Don't raise here as this is not critical for the main functionality

    def clear_quota_cache(self):
        """Clear the quota cache."""
        self._quota_cache = {}

    async def cleanup_old_usage_records(self, days_to_keep: int = 90):
        """Clean up old usage records."""
        try:
            app_logger.info(f"Cleaning up usage records older than {days_to_keep} days")
            
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
            
            # Delete old records
            result = LLMUsage.objects(
                timestamp__lt=cutoff_date
            ).delete()
            
            app_logger.info(f"Deleted {result} old usage records")
            
        except Exception as e:
            error_logger.error(f"Failed to cleanup old usage records: {str(e)}", exc_info=True)
            raise