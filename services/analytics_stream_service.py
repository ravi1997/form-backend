from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from config.settings import settings
from logger.unified_logger import app_logger, error_logger


class AnalyticsStreamService:
    """
    Consumes submission events and exports normalized metrics to an OLAP database.
    DuckDB writes are partitioned into one Parquet file per batch and read back
    through a hive-partitioned view.
    """

    def __init__(self):
        from threading import Lock

        self._lock = Lock()
        self.engine_type = settings.OLAP_ENGINE
        self._conn = None
        self._view_initialized = False
        duckdb_base = Path(settings.DUCKDB_PATH)
        self._partition_root = duckdb_base.parent / f"{duckdb_base.stem}_partitions"

    def _get_connection(self):
        with self._lock:
            if self._conn is not None:
                return self._conn

            app_logger.info(
                f"AnalyticsStreamService: Initializing connection to {self.engine_type}"
            )
            try:
                if self.engine_type == "duckdb":
                    import duckdb

                    self._conn = duckdb.connect(settings.DUCKDB_PATH)
                    self._conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS submission_analytics_archive (
                            id VARCHAR,
                            form_id VARCHAR,
                            organization_id VARCHAR,
                            submitted_at TIMESTAMP,
                            status VARCHAR,
                            field_count INTEGER,
                            processing_time_ms DOUBLE,
                            batch_uuid VARCHAR,
                            year INTEGER,
                            month INTEGER,
                            day INTEGER
                        )
                        """
                    )
                elif self.engine_type == "clickhouse":
                    from clickhouse_driver import Client

                    self._conn = Client.from_url(settings.CLICKHOUSE_URL)
                    self._conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS submission_analytics (
                            id String,
                            form_id String,
                            organization_id String,
                            submitted_at DateTime,
                            status String,
                            field_count UInt32,
                            processing_time_ms Float64,
                            batch_uuid String,
                            year UInt16,
                            month UInt8,
                            day UInt8
                        ) ENGINE = MergeTree()
                        ORDER BY (organization_id, submitted_at, form_id)
                        """
                    )

                app_logger.info(
                    f"AnalyticsStreamService: Successfully connected to {self.engine_type}"
                )
                return self._conn
            except Exception as e:
                error_logger.error(
                    f"AnalyticsStreamService: Failed to connect to {self.engine_type}: {str(e)}",
                    exc_info=True,
                )
                raise

    def _initialize_partition_view(self):
        with self._lock:
            if self.engine_type != "duckdb" or self._view_initialized:
                return
            self._partition_root.mkdir(parents=True, exist_ok=True)
            self._conn.execute(
                f"""
                CREATE OR REPLACE VIEW submission_analytics AS
                SELECT *
                FROM read_parquet('{self._partition_root.as_posix()}/**/*.parquet', hive_partitioning = 1)
                """
            )
            self._view_initialized = True

    def _normalize_event(self, event_payload: Dict[str, Any]) -> Dict[str, Any]:
        data = event_payload.get("data", {})
        submitted_at_raw = event_payload.get("timestamp")
        submitted_at = submitted_at_raw
        if isinstance(submitted_at_raw, str):
            submitted_at = datetime.fromisoformat(submitted_at_raw.replace("Z", "+00:00"))
        if not isinstance(submitted_at, datetime):
            submitted_at = datetime.now(timezone.utc)
        if submitted_at.tzinfo is None:
            submitted_at = submitted_at.replace(tzinfo=timezone.utc)

        day_bucket = submitted_at.date()
        return {
            "id": event_payload.get("response_id"),
            "form_id": event_payload.get("form_id"),
            "organization_id": event_payload.get("organization_id"),
            "submitted_at": submitted_at,
            "status": "submitted",
            "field_count": len(data),
            "processing_time_ms": 0.0,
            "batch_uuid": str(uuid4()),
            "year": day_bucket.year,
            "month": day_bucket.month,
            "day": day_bucket.day,
        }

    def process_submission_event(self, event_payload: Dict[str, Any]):
        """Normalizes a form submission event and inserts it into the OLAP store."""
        app_logger.info("AnalyticsStreamService: Processing submission event")
        try:
            normalized_row = self._normalize_event(event_payload)
            self._insert_row(normalized_row)
            app_logger.debug(
                f"AnalyticsStreamService: Exported analytics for response {normalized_row['id']} to {self.engine_type}"
            )
            app_logger.info(
                "AnalyticsStreamService: Successfully processed submission event"
            )
        except Exception as e:
            error_logger.error(
                f"AnalyticsStreamService: Failed to process analytics stream event: {str(e)}",
                exc_info=True,
            )
            raise

    def _insert_row(self, row: Dict[str, Any]):
        app_logger.debug(
            f"AnalyticsStreamService: Inserting row into {self.engine_type}"
        )
        conn = self._get_connection()
        try:
            if self.engine_type == "duckdb":
                partition_dir = (
                    self._partition_root
                    / str(row["organization_id"])
                    / str(row["year"])
                    / f"{int(row['month']):02d}"
                    / f"{int(row['day']):02d}"
                )
                partition_dir.mkdir(parents=True, exist_ok=True)
                file_path = partition_dir / f"{row['batch_uuid']}.parquet"
                conn.execute(
                    f"""
                    COPY (
                        SELECT
                            ? AS id,
                            ? AS form_id,
                            ? AS organization_id,
                            ? AS submitted_at,
                            ? AS status,
                            ? AS field_count,
                            ? AS processing_time_ms,
                            ? AS batch_uuid,
                            ? AS year,
                            ? AS month,
                            ? AS day
                    ) TO '{file_path.as_posix()}' (FORMAT PARQUET)
                    """,
                    [
                        row["id"],
                        row["form_id"],
                        row["organization_id"],
                        row["submitted_at"],
                        row["status"],
                        row["field_count"],
                        row["processing_time_ms"],
                        row["batch_uuid"],
                        row["year"],
                        row["month"],
                        row["day"],
                    ],
                )
                self._initialize_partition_view()
                conn.execute(
                    """
                    INSERT INTO submission_analytics_archive VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        row["id"],
                        row["form_id"],
                        row["organization_id"],
                        row["submitted_at"],
                        row["status"],
                        row["field_count"],
                        row["processing_time_ms"],
                        row["batch_uuid"],
                        row["year"],
                        row["month"],
                        row["day"],
                    ],
                )
            elif self.engine_type == "clickhouse":
                conn.execute("INSERT INTO submission_analytics VALUES", [row])
        except Exception as e:
            error_logger.error(
                f"AnalyticsStreamService: Insertion failed: {str(e)}", exc_info=True
            )
            raise

    def _has_partition_files(self) -> bool:
        return self._partition_root.exists() and any(
            self._partition_root.rglob("*.parquet")
        )

    def refresh_partition_view(self):
        if self.engine_type == "duckdb":
            self._initialize_partition_view()

    def get_submission_trends(
        self, organization_id: str, days: int = 7
    ) -> List[Dict[str, Any]]:
        """Queries the OLAP engine for daily submission counts."""
        app_logger.info(
            f"AnalyticsStreamService: Getting submission trends for org {organization_id} over {days} days"
        )
        try:
            conn = self._get_connection()
            if self.engine_type == "duckdb":
                safe_days = max(int(days), 1)
                if not self._has_partition_files():
                    return []
                res = conn.execute(
                    """
                    SELECT CAST(submitted_at AS DATE) as day, count(*) as count
                    FROM submission_analytics
                    WHERE organization_id = ?
                      AND submitted_at >= NOW() - (? * INTERVAL 1 DAY)
                    GROUP BY CAST(submitted_at AS DATE)
                    ORDER BY day DESC
                    """,
                    [organization_id, safe_days],
                ).fetchall()
                result = [{"day": str(r[0]), "count": r[1]} for r in res]
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
                res = conn.execute(
                    query, {"organization_id": organization_id, "days": safe_days}
                )
                result = [{"day": str(r[0]), "count": r[1]} for r in res]
            else:
                result = []

            app_logger.info(
                f"AnalyticsStreamService: Successfully retrieved {len(result)} trend data points"
            )
            return result
        except Exception as e:
            error_logger.error(
                f"AnalyticsStreamService: Failed to get submission trends: {str(e)}",
                exc_info=True,
            )
            return []


analytics_stream_service = AnalyticsStreamService()
