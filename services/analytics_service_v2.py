from typing import Dict, Any, List, Optional
from mongoengine import QuerySet
from models.Response import FormResponse
from models.Form import Form
from datetime import datetime, timedelta, timezone
from logger.unified_logger import app_logger


class AnalyticsService:
    """
    High-performance analytics service using MongoDB aggregation pipelines.
    All queries are optimized with proper indexing and organization filtering.
    """

    @staticmethod
    def get_analytics_summary(form_id: str, organization_id: str) -> Dict[str, Any]:
        """
        Get analytics summary using MongoDB aggregation.

        Aggregation Pipeline:
        1. $match: Filter by form_id, organization_id, and is_deleted=false
        2. $group: Count total, find last submission, collect all statuses
        3. $project: Shape the output
        """
        app_logger.info(
            f"Getting analytics summary for form_id: {form_id}, org: {organization_id}"
        )

        pipeline = [
            {
                "$match": {
                    "form": form_id,
                    "organization_id": organization_id,
                    "is_deleted": False,
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "last_submitted_at": {"$max": "$submitted_at"},
                    "last_submitted_by": {"$last": "$submitted_by"},
                    "statuses": {"$push": {"$ifNull": ["$status", "submitted"]}},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "total": 1,
                    "last_submitted_at": 1,
                    "last_submitted_by": 1,
                    "statuses": 1,
                }
            },
        ]

        result = list(FormResponse.objects(__raw__=pipeline))

        if not result:
            return {
                "total_responses": 0,
                "status_breakdown": {},
                "last_submitted_at": None,
                "last_submitted_by": None,
            }

        summary = result[0]

        # Build status breakdown from the array
        from collections import Counter

        status_counts = Counter(summary["statuses"])
        status_breakdown = dict(status_counts)

        app_logger.info(
            f"Analytics summary completed for form_id: {form_id}: {summary['total']} responses"
        )

        return {
            "total_responses": summary["total"],
            "status_breakdown": status_breakdown,
            "last_submitted_at": summary["last_submitted_at"].isoformat()
            if summary["last_submitted_at"]
            else None,
            "last_submitted_by": summary["last_submitted_by"],
        }

    @staticmethod
    def get_analytics_timeline(
        form_id: str, organization_id: str, days: int = 30
    ) -> Dict[str, Any]:
        """
        Get analytics timeline using MongoDB aggregation.

        Aggregation Pipeline:
        1. $match: Filter by form_id, organization_id, is_deleted=false, and date range
        2. $project: Extract date components
        3. $group: Group by date string
        4. $sort: Chronological order
        """
        app_logger.info(
            f"Getting analytics timeline for form_id: {form_id}, org: {organization_id}, days: {days}"
        )

        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        pipeline = [
            {
                "$match": {
                    "form": form_id,
                    "organization_id": organization_id,
                    "is_deleted": False,
                    "submitted_at": {"$gte": start_date},
                }
            },
            {
                "$project": {
                    "date_str": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$submitted_at",
                            "timezone": "UTC",
                        }
                    },
                }
            },
            {
                "$group": {
                    "_id": "$date_str",
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]

        timeline_data = list(FormResponse.objects(__raw__=pipeline))
        timeline = [
            {"date": item["_id"], "count": item["count"]} for item in timeline_data
        ]

        app_logger.info(
            f"Analytics timeline completed for form_id: {form_id}: {len(timeline)} data points"
        )

        return {"period_days": days, "timeline": timeline}

    @staticmethod
    def get_analytics_distribution(
        form_id: str, organization_id: str, form: Form
    ) -> Dict[str, Any]:
        """
        Get analytics distribution using MongoDB aggregation.

        Aggregation Pipeline:
        1. $match: Filter by form_id, organization_id, is_deleted=false
        2. $project: Extract only data field
        3. $unwind: Unwind data into individual fields
        4. $group: Group by question_id and values
        """
        app_logger.info(
            f"Getting analytics distribution for form_id: {form_id}, org: {organization_id}"
        )

        if not form.versions:
            return {"distribution": []}

        latest_version = form.versions[-1]
        choice_questions = {}
        target_types = ["radio", "select", "checkbox", "rating", "boolean"]

        for section in latest_version.sections:
            sid = str(section.id)
            for q in section.questions:
                if q.field_type in target_types:
                    choice_questions[str(q.id)] = {
                        "label": q.label,
                        "sid": sid,
                        "type": q.field_type,
                    }

        if not choice_questions:
            return {"distribution": []}

        # Unwind data structure to flatten it for aggregation
        pipeline = [
            {
                "$match": {
                    "form": form_id,
                    "organization_id": organization_id,
                    "is_deleted": False,
                }
            },
            {
                "$project": {"data": 1},
            },
            {
                "$unwind": "$data",
            },
            {
                "$unwind": "$data",
            },
            {
                "$group": {
                    "_id": {
                        "qid": "$key",
                        "value": "$value",
                    },
                    "count": {"$sum": 1},
                }
            },
            {
                "$sort": {"count": -1},
            },
        ]

        distribution_results = list(FormResponse.objects(__raw__=pipeline))

        # Format results for frontend
        formatted_distribution = []
        for item in distribution_results:
            qid = item["_id"]["qid"]
            if qid in choice_questions:
                formatted_distribution.append(
                    {
                        "question_id": qid,
                        "label": choice_questions[qid]["label"],
                        "type": choice_questions[qid]["type"],
                        "counts": {item["_id"]["value"]: item["count"]},
                    }
                )

        app_logger.info(
            f"Analytics distribution completed for form_id: {form_id}: {len(formatted_distribution)} questions"
        )

        return {"distribution": formatted_distribution}
