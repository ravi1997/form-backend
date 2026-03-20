import logging
import json
from typing import Dict, Any, List
from config.settings import settings

logger = logging.getLogger(__name__)

class AnalyticsStreamService:
    """
    Consumes submission events and exports normalized metrics to an OLAP database.
    Decouples analytics processing from the MongoDB transactional engine.
    """

    def __init__(self):
        self.engine_type = settings.OLAP_ENGINE
        self._conn = None

    def _get_connection(self):
        if self._conn is not None:
            return self._conn
            
        if self.engine_type == "duckdb":
            import duckdb
            self._conn = duckdb.connect(settings.DUCKDB_PATH)
            # Initialize schema if needed
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS submission_analytics (
                    id VARCHAR PRIMARY KEY,
                    form_id VARCHAR,
                    organization_id VARCHAR,
                    submitted_at TIMESTAMP,
                    status VARCHAR,
                    field_count INTEGER,
                    processing_time_ms DOUBLE
                )
            """)
        elif self.engine_type == "clickhouse":
            from clickhouse_driver import Client
            self._conn = Client.from_url(settings.CLICKHOUSE_URL)
            # ClickHouse schema initialization would usually be out-of-band
            
        return self._conn

    def process_submission_event(self, event_payload: Dict[str, Any]):
        """Normalizes a form submission event and inserts it into the OLAP store."""
        try:
            # Flatten/Normalize for columnar storage
            data = event_payload.get("data", {})
            normalized_row = {
                "id": event_payload.get("response_id"),
                "form_id": event_payload.get("form_id"),
                "organization_id": event_payload.get("organization_id"),
                "submitted_at": event_payload.get("timestamp"),
                "status": "submitted",
                "field_count": len(data),
                "processing_time_ms": 0.0 # Could be calculated
            }
            
            self._insert_row(normalized_row)
            logger.debug(f"Exported analytics for response {normalized_row['id']} to {self.engine_type}")
        except Exception as e:
            logger.error(f"Failed to process analytics stream event: {e}", exc_info=True)

    def _insert_row(self, row: Dict[str, Any]):
        conn = self._get_connection()
        if self.engine_type == "duckdb":
            # Using placeholders for safety
            keys = ", ".join(row.keys())
            placeholders = ", ".join(["?"] * len(row))
            values = tuple(row.values())
            conn.execute(f"INSERT OR IGNORE INTO submission_analytics ({keys}) VALUES ({placeholders})", values)
        elif self.engine_type == "clickhouse":
            conn.execute("INSERT INTO submission_analytics VALUES", [row])

    def get_submission_trends(self, organization_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Queries the OLAP engine for daily submission counts."""
        conn = self._get_connection()
        if self.engine_type == "duckdb":
            safe_days = max(int(days), 1)
            res = conn.execute(
                """
                SELECT CAST(submitted_at AS DATE) as day, count(*) as count
                FROM submission_analytics
                WHERE organization_id = ?
                  AND submitted_at >= NOW() - (? * INTERVAL 1 DAY)
                GROUP BY day
                ORDER BY day DESC
                """,
                [organization_id, safe_days],
            ).fetchall()
            return [{"day": str(r[0]), "count": r[1]} for r in res]
        elif self.engine_type == "clickhouse":
            safe_days = max(int(days), 1)
            query = """
                SELECT toDate(submitted_at) as day, count(*) as count
                FROM submission_analytics
                WHERE organization_id = %(organization_id)s
                  AND submitted_at >= now() - INTERVAL %(days)s DAY
                GROUP BY day
                ORDER BY day DESC
            """
            res = conn.execute(query, {"organization_id": organization_id, "days": safe_days})
            return [{"day": str(r[0]), "count": r[1]} for r in res]
        return []

analytics_stream_service = AnalyticsStreamService()
