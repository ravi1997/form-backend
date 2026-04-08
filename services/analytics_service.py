from typing import Dict, Any, Optional, List
from mongoengine import QuerySet
from models.Response import FormResponse
from models.Form import Form
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter
from logger.unified_logger import app_logger


class AnalyticsService:
    """
    Service for analytics operations using MongoDB aggregation pipelines.
    All logic moved from Python-side loops to efficient MongoDB aggregations.
    """

    @staticmethod
    def get_analytics_summary(form_id: str, organization_id: str) -> Dict[str, Any]:
        """
        Get analytics summary using MongoDB aggregation.
        Returns total responses, status breakdown, and last submission.
        """
        app_logger.info(f"Entering get_analytics_summary for form_id: {form_id}")

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
                    "status_breakdown": {
                        "$push": {"$ifNull": ["$status", "submitted"]}
                    },
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "total": 1,
                    "last_submitted_at": 1,
                    "status_breakdown": 1,
                }
            },
        ]

        result = list(FormResponse.objects(__raw__=pipeline))
        app_logger.info(
            f"Exiting get_analytics_summary successfully for form_id: {form_id}"
        )

        if not result:
            return {
                "total_responses": 0,
                "status_breakdown": {},
                "last_submitted_at": None,
            }

        summary = result[0]
        status_counts = defaultdict(int)
        for status in summary["status_breakdown"]:
            status_counts[status] += 1

        return {
            "total_responses": summary["total"],
            "status_breakdown": dict(status_counts),
            "last_submitted_at": summary["last_submitted_at"].isoformat()
            if summary["last_submitted_at"]
            else None,
        }

    @staticmethod
    def get_analytics_timeline(
        form_id: str, organization_id: str, days: int = 30
    ) -> Dict[str, Any]:
        """
        Get analytics timeline using MongoDB aggregation.
        Groups submissions by date over a configurable period.
        """
        app_logger.info(
            f"Entering get_analytics_timeline for form_id: {form_id}, days: {days}"
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
                "$group": {
                    "_id": {
                        "date": {
                            "$dateToString": {
                                "format": "%Y-%m-%d",
                                "date": "$submitted_at",
                            }
                        },
                    },
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id.date": 1}},
            {
                "$project": {
                    "_id": 0,
                    "date": "$_id.date",
                    "count": 1,
                }
            },
        ]

        result = list(FormResponse.objects(__raw__=pipeline))
        timeline = [{"date": item["date"], "count": item["count"]} for item in result]

        app_logger.info(
            f"Exiting get_analytics_timeline successfully for form_id: {form_id}"
        )
        return {"period_days": days, "timeline": timeline}

    @staticmethod
    def get_analytics_distribution(
        form_id: str, organization_id: str, form: Form
    ) -> Dict[str, Any]:
        """
        Get analytics distribution using MongoDB aggregation.
        Groups responses by question values for choice-based questions.
        """
        app_logger.info(f"Entering get_analytics_distribution for form_id: {form_id}")

        if not form.versions:
            return {"distribution": []}

        latest_version = form.versions[-1]
        sections = latest_version.resolved_snapshot.get("sections", []) if hasattr(latest_version, "resolved_snapshot") else []
        choice_questions = {}
        target_types = ["radio", "select", "checkbox", "rating", "boolean"]

        for section in sections:
            sid = str(section.get("id"))
            for q in section.get("questions", []):
                if q.get("field_type") in target_types:
                    choice_questions[str(q.get("id"))] = {
                        "label": q.get("label"),
                        "sid": sid,
                        "type": q.get("field_type"),
                    }

        if not choice_questions:
            return {"distribution": []}

        pipeline = [
            {
                "$match": {
                    "form": form_id,
                    "organization_id": organization_id,
                    "is_deleted": False,
                }
            },
            {"$project": {"data": 1, "_id": 0}},
        ]

        responses = list(FormResponse.objects(__raw__=pipeline))
        distribution = defaultdict(Counter)

        for r in responses:
            data = r.get("data", {})
            for qid, info in choice_questions.items():
                sid = info["sid"]
                section_data = data.get(sid)

                if not section_data:
                    continue

                entries = (
                    section_data if isinstance(section_data, list) else [section_data]
                )

                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    val = entry.get(qid)

                    if val is None or val == "":
                        continue

                    if isinstance(val, list):
                        for v in val:
                            distribution[qid][str(v)] += 1
                    else:
                        distribution[qid][str(val)] += 1

        results = []
        for qid, counts in distribution.items():
            results.append(
                {
                    "question_id": qid,
                    "label": choice_questions[qid]["label"],
                    "type": choice_questions[qid]["type"],
                    "counts": dict(counts),
                }
            )

        app_logger.info(
            f"Exiting get_analytics_distribution successfully for form_id: {form_id}"
        )
        return {"distribution": results}
