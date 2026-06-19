"""
services/llm_usage_tracking_service.py
Service for tracking LLM usage and costs across the platform.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import uuid

from logger.unified_logger import app_logger, error_logger
from models.llm_model import LLMUsage, LLMOrganizationQuota
from utils.exceptions import ValidationError, QuotaExceededError


class UsagePeriod(Enum):
    """Usage aggregation periods."""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class LLMUsageTrackingService:
    """Service for tracking LLM usage and costs."""

    def __init__(self):
        self._usage_cache = {}  # Cache for recent usage data

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
        """Track LLM usage for a request."""
        try:
            app_logger.info(f"Tracking LLM usage for org {organization_id}: {prompt_tokens} + {completion_tokens} tokens")
            
            # Check quota first
            await self._check_quota(organization_id, cost)
            
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
                metadata=metadata or {},
                timestamp=datetime.utcnow()
            )
            usage.save()
            
            # Update cache
            cache_key = f"{organization_id}:{datetime.utcnow().strftime('%Y-%m-%d')}"
            if cache_key not in self._usage_cache:
                self._usage_cache[cache_key] = {
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "request_count": 0
                }
            
            self._usage_cache[cache_key]["total_tokens"] += usage.total_tokens
            self._usage_cache[cache_key]["total_cost"] += usage.cost
            self._usage_cache[cache_key]["request_count"] += 1
            
            # Update organization quota
            await self._update_quota_usage(organization_id, cost)
            
            app_logger.info(f"Successfully tracked LLM usage: {usage.id}")
            return usage
            
        except QuotaExceededError:
            raise
        except Exception as e:
            error_logger.error(f"Failed to track LLM usage: {str(e)}", exc_info=True)
            raise

    async def get_usage_stats(
        self,
        organization_id: str,
        start_date: datetime = None,
        end_date: datetime = None,
        period: UsagePeriod = UsagePeriod.DAILY,
        provider: str = None,
        model_id: str = None
    ) -> Dict[str, Any]:
        """Get usage statistics for an organization."""
        try:
            app_logger.info(f"Getting usage stats for org {organization_id}")
            
            # Set default date range
            if not end_date:
                end_date = datetime.utcnow()
            
            if not start_date:
                if period == UsagePeriod.HOURLY:
                    start_date = end_date - timedelta(hours=24)
                elif period == UsagePeriod.DAILY:
                    start_date = end_date - timedelta(days=30)
                elif period == UsagePeriod.WEEKLY:
                    start_date = end_date - timedelta(weeks=12)
                elif period == UsagePeriod.MONTHLY:
                    start_date = end_date - timedelta(days=365)
            
            # Build query
            query = LLMUsage.objects(
                organization_id=organization_id,
                timestamp__gte=start_date,
                timestamp__lte=end_date
            )
            
            if provider:
                query = query.filter(provider=provider)
            
            if model_id:
                query = query.filter(model_id=model_id)
            
            # Get usage records
            usage_records = query.order_by("timestamp")
            
            # Aggregate data
            stats = {
                "total_tokens": 0,
                "total_cost": 0.0,
                "request_count": 0,
                "avg_tokens_per_request": 0,
                "avg_cost_per_request": 0.0,
                "period": period.value,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "by_provider": {},
                "by_model": {},
                "by_period": {}
            }
            
            for usage in usage_records:
                stats["total_tokens"] += usage.total_tokens
                stats["total_cost"] += usage.cost
                stats["request_count"] += 1
                
                # Aggregate by provider
                if usage.provider not in stats["by_provider"]:
                    stats["by_provider"][usage.provider] = {
                        "total_tokens": 0,
                        "total_cost": 0.0,
                        "request_count": 0
                    }
                
                stats["by_provider"][usage.provider]["total_tokens"] += usage.total_tokens
                stats["by_provider"][usage.provider]["total_cost"] += usage.cost
                stats["by_provider"][usage.provider]["request_count"] += 1
                
                # Aggregate by model
                model_key = f"{usage.provider}:{usage.model_id}"
                if model_key not in stats["by_model"]:
                    stats["by_model"][model_key] = {
                        "total_tokens": 0,
                        "total_cost": 0.0,
                        "request_count": 0
                    }
                
                stats["by_model"][model_key]["total_tokens"] += usage.total_tokens
                stats["by_model"][model_key]["total_cost"] += usage.cost
                stats["by_model"][model_key]["request_count"] += 1
            
            # Calculate averages
            if stats["request_count"] > 0:
                stats["avg_tokens_per_request"] = stats["total_tokens"] / stats["request_count"]
                stats["avg_cost_per_request"] = stats["total_cost"] / stats["request_count"]
            
            # Aggregate by period
            stats["by_period"] = self._aggregate_by_period(usage_records, period)
            
            app_logger.info(f"Successfully retrieved usage stats for org {organization_id}")
            return stats
            
        except Exception as e:
            error_logger.error(f"Failed to get usage stats: {str(e)}", exc_info=True)
            raise

    async def get_quota_info(self, organization_id: str) -> Dict[str, Any]:
        """Get quota information for an organization."""
        try:
            app_logger.info(f"Getting quota info for org {organization_id}")
            
            # Get quota
            quota = LLMOrganizationQuota.objects(
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not quota:
                # Create default quota
                quota = await self._create_default_quota(organization_id)
            
            # Get current usage for this period
            current_period_start = self._get_period_start(quota.period_type)
            current_usage = await self.get_usage_stats(
                organization_id=organization_id,
                start_date=current_period_start,
                period=UsagePeriod.DAILY  # Always get daily for current period
            )
            
            # Calculate remaining quota
            remaining_quota = quota.monthly_limit - current_usage["total_cost"]
            usage_percentage = (current_usage["total_cost"] / quota.monthly_limit) * 100 if quota.monthly_limit > 0 else 0
            
            result = {
                "organization_id": organization_id,
                "monthly_limit": quota.monthly_limit,
                "current_usage": current_usage["total_cost"],
                "remaining_quota": remaining_quota,
                "usage_percentage": usage_percentage,
                "period_type": quota.period_type,
                "period_start": current_period_start.isoformat(),
                "period_end": self._get_period_end(quota.period_type).isoformat(),
                "warning_threshold": quota.warning_threshold,
                "is_over_limit": remaining_quota < 0,
                "is_near_limit": usage_percentage >= quota.warning_threshold
            }
            
            app_logger.info(f"Successfully retrieved quota info for org {organization_id}")
            return result
            
        except Exception as e:
            error_logger.error(f"Failed to get quota info: {str(e)}", exc_info=True)
            raise

    async def set_quota(
        self,
        organization_id: str,
        monthly_limit: float,
        warning_threshold: float = 80.0,
        period_type: str = "monthly",
        updated_by: str = None
    ) -> LLMOrganizationQuota:
        """Set quota for an organization."""
        try:
            app_logger.info(f"Setting quota for org {organization_id}: ${monthly_limit}")
            
            # Get or create quota
            quota = LLMOrganizationQuota.objects(
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if quota:
                # Update existing quota
                quota.monthly_limit = monthly_limit
                quota.warning_threshold = warning_threshold
                quota.period_type = period_type
                quota.updated_by = updated_by
                quota.updated_at = datetime.utcnow()
                quota.save()
            else:
                # Create new quota
                quota = LLMOrganizationQuota(
                    organization_id=organization_id,
                    monthly_limit=monthly_limit,
                    warning_threshold=warning_threshold,
                    period_type=period_type,
                    created_by=updated_by
                )
                quota.save()
            
            app_logger.info(f"Successfully set quota for org {organization_id}")
            return quota
            
        except Exception as e:
            error_logger.error(f"Failed to set quota: {str(e)}", exc_info=True)
            raise

    async def get_cost_forecast(
        self,
        organization_id: str,
        forecast_days: int = 30
    ) -> Dict[str, Any]:
        """Generate cost forecast based on historical usage."""
        try:
            app_logger.info(f"Generating cost forecast for org {organization_id}")
            
            # Get historical usage for the last 30 days
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=30)
            
            historical_stats = await self.get_usage_stats(
                organization_id=organization_id,
                start_date=start_date,
                end_date=end_date,
                period=UsagePeriod.DAILY
            )
            
            # Calculate daily average
            daily_usage = historical_stats["by_period"].get("daily", [])
            daily_avg_cost = 0.0
            
            if daily_usage:
                total_daily_cost = sum(day["total_cost"] for day in daily_usage)
                daily_avg_cost = total_daily_cost / len(daily_usage)
            
            # Generate forecast
            forecast_start = end_date
            forecast_end = forecast_start + timedelta(days=forecast_days)
            
            forecast = {
                "forecast_days": forecast_days,
                "daily_average_cost": daily_avg_cost,
                "forecast_total_cost": daily_avg_cost * forecast_days,
                "forecast_start": forecast_start.isoformat(),
                "forecast_end": forecast_end.isoformat(),
                "historical_period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "total_cost": historical_stats["total_cost"]
                }
            }
            
            # Get current quota
            quota_info = await self.get_quota_info(organization_id)
            forecast["quota_info"] = quota_info
            
            # Check if forecast exceeds quota
            if quota_info["monthly_limit"] > 0:
                current_period_end = datetime.fromisoformat(quota_info["period_end"].replace("Z", "+00:00"))
                remaining_days = (current_period_end - end_date).days
                
                if remaining_days > 0:
                    forecast_remaining_cost = daily_avg_cost * remaining_days
                    projected_total = quota_info["current_usage"] + forecast_remaining_cost
                    
                    forecast["projected_monthly_total"] = projected_total
                    forecast["will_exceed_quota"] = projected_total > quota_info["monthly_limit"]
                    forecast["projected_overage"] = max(0, projected_total - quota_info["monthly_limit"])
            
            app_logger.info(f"Successfully generated cost forecast for org {organization_id}")
            return forecast
            
        except Exception as e:
            error_logger.error(f"Failed to generate cost forecast: {str(e)}", exc_info=True)
            raise

    async def _check_quota(self, organization_id: str, cost: float):
        """Check if organization has sufficient quota."""
        try:
            quota_info = await self.get_quota_info(organization_id)
            
            if quota_info["is_over_limit"]:
                raise QuotaExceededError(f"Organization {organization_id} has exceeded LLM quota")
            
            # Check if this request would exceed quota
            if quota_info["remaining_quota"] < cost:
                raise QuotaExceededError(f"Request cost ${cost} would exceed remaining quota ${quota_info['remaining_quota']}")
            
        except Exception as e:
            if isinstance(e, QuotaExceededError):
                raise
            error_logger.error(f"Failed to check quota: {str(e)}", exc_info=True)
            raise

    async def _update_quota_usage(self, organization_id: str, cost: float):
        """Update quota usage for an organization."""
        try:
            # This is a simplified implementation
            # In production, you might want to maintain a separate usage counter
            # that's updated atomically to avoid race conditions
            
            quota = LLMOrganizationQuota.objects(
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if quota:
                quota.current_usage = (quota.current_usage or 0) + cost
                quota.updated_at = datetime.utcnow()
                quota.save()
            
        except Exception as e:
            error_logger.error(f"Failed to update quota usage: {str(e)}", exc_info=True)
            # Don't raise here as this is not critical for the main functionality

    async def _create_default_quota(self, organization_id: str) -> LLMOrganizationQuota:
        """Create default quota for an organization."""
        try:
            quota = LLMOrganizationQuota(
                organization_id=organization_id,
                monthly_limit=100.0,  # $100 default monthly limit
                warning_threshold=80.0,
                period_type="monthly"
            )
            quota.save()
            return quota
            
        except Exception as e:
            error_logger.error(f"Failed to create default quota: {str(e)}", exc_info=True)
            raise

    def _get_period_start(self, period_type: str) -> datetime:
        """Get start date for current period."""
        now = datetime.utcnow()
        
        if period_type == "monthly":
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period_type == "weekly":
            # Start from Monday
            days_since_monday = now.weekday()
            return now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
        else:  # daily
            return now.replace(hour=0, minute=0, second=0, microsecond=0)

    def _get_period_end(self, period_type: str) -> datetime:
        """Get end date for current period."""
        now = datetime.utcnow()
        
        if period_type == "monthly":
            if now.month == 12:
                return now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                return now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period_type == "weekly":
            # End on Sunday
            days_until_sunday = 6 - now.weekday()
            return now.replace(hour=23, minute=59, second=59, microsecond=999999) + timedelta(days=days_until_sunday)
        else:  # daily
            return now.replace(hour=23, minute=59, second=59, microsecond=999999)

    def _aggregate_by_period(self, usage_records, period: UsagePeriod) -> Dict[str, Any]:
        """Aggregate usage records by period."""
        aggregated = {"hourly": [], "daily": [], "weekly": [], "monthly": []}
        
        # Group records by period
        period_groups = {}
        
        for usage in usage_records:
            timestamp = usage.timestamp
            
            if period == UsagePeriod.HOURLY:
                key = timestamp.strftime("%Y-%m-%d %H:00")
            elif period == UsagePeriod.DAILY:
                key = timestamp.strftime("%Y-%m-%d")
            elif period == UsagePeriod.WEEKLY:
                # Get Monday of the week
                monday = timestamp - timedelta(days=timestamp.weekday())
                key = monday.strftime("%Y-%m-%d")
            else:  # monthly
                key = timestamp.strftime("%Y-%m")
            
            if key not in period_groups:
                period_groups[key] = []
            period_groups[key].append(usage)
        
        # Aggregate each period
        for period_key, records in period_groups.items():
            period_data = {
                "period": period_key,
                "total_tokens": sum(r.total_tokens for r in records),
                "total_cost": sum(r.cost for r in records),
                "request_count": len(records)
            }
            
            if period == UsagePeriod.HOURLY:
                aggregated["hourly"].append(period_data)
            elif period == UsagePeriod.DAILY:
                aggregated["daily"].append(period_data)
            elif period == UsagePeriod.WEEKLY:
                aggregated["weekly"].append(period_data)
            else:  # monthly
                aggregated["monthly"].append(period_data)
        
        # Sort by period
        for key in aggregated:
            aggregated[key].sort(key=lambda x: x["period"])
        
        return aggregated