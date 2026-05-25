"""
Migration 001: Add compound indexes, TTL indexes, and backfill organization_id on SnapshotStore.

Run with:
    python scripts/migrations/001_add_compound_indexes.py

Idempotent — safe to run multiple times. All index creations use background=True.
"""

import os
import sys
import logging

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from pymongo import IndexModel, ASCENDING, DESCENDING

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/ridp_dev")


def _create_indexes(collection, indexes, label):
    """Helper that logs and creates each index, skipping conflicts."""
    for idx in indexes:
        try:
            collection.create_indexes([idx], background=True)
            logger.info(f"  ✅ {label}: {idx.document['name']}")
        except Exception as e:
            if "already exists" in str(e).lower() or "IndexOptionsConflict" in str(type(e)):
                logger.info(f"  ⏭  {label}: {idx.document.get('name', '?')} (already exists)")
            else:
                logger.warning(f"  ⚠  {label}: {e}")


def run():
    from pymongo import MongoClient

    logger.info(f"Connecting to: {MONGODB_URI[:40]}...")
    client = MongoClient(MONGODB_URI)
    db_name = MONGODB_URI.rsplit("/", 1)[-1].split("?")[0]
    db = client[db_name]
    logger.info(f"Database: {db_name}")

    # ── 1. forms ────────────────────────────────────────────────────────────────
    logger.info("forms collection:")
    _create_indexes(db["forms"], [
        IndexModel(
            [("organization_id", ASCENDING), ("is_deleted", ASCENDING), ("created_at", DESCENDING)],
            name="org_not_deleted_created",
        ),
        IndexModel(
            [("organization_id", ASCENDING), ("status", ASCENDING), ("is_deleted", ASCENDING)],
            name="org_status_not_deleted",
        ),
        IndexModel(
            [("organization_id", ASCENDING), ("slug", ASCENDING)],
            name="org_slug",
            unique=True,
            sparse=True,
        ),
    ], "forms")

    # ── 2. form_responses ───────────────────────────────────────────────────────
    logger.info("form_responses collection:")
    _create_indexes(db["form_responses"], [
        IndexModel(
            [("organization_id", ASCENDING), ("form", ASCENDING),
             ("is_deleted", ASCENDING), ("submitted_at", DESCENDING)],
            name="org_form_not_deleted_submitted",
        ),
        IndexModel(
            [("organization_id", ASCENDING), ("idempotency_key", ASCENDING)],
            name="org_idempotency_key",
            unique=True,
            sparse=True,
        ),
    ], "form_responses")

    # ── 3. form_snapshots ───────────────────────────────────────────────────────
    logger.info("form_snapshots collection:")
    _create_indexes(db["form_snapshots"], [
        IndexModel(
            [("created_at", ASCENDING)],
            name="ttl_90_days",
            expireAfterSeconds=7776000,   # 90 days
        ),
        IndexModel(
            [("organization_id", ASCENDING), ("form_id", ASCENDING), ("created_at", DESCENDING)],
            name="org_form_id_created",
        ),
    ], "form_snapshots")

    # ── 4. idempotency_records ──────────────────────────────────────────────────
    logger.info("idempotency_records collection:")
    _create_indexes(db["idempotency_records"], [
        IndexModel(
            [("expires_at", ASCENDING)],
            name="ttl_expiry",
            expireAfterSeconds=0,
        ),
        IndexModel(
            [("organization_id", ASCENDING), ("key", ASCENDING)],
            name="org_key_unique",
            unique=True,
            sparse=True,
        ),
    ], "idempotency_records")

    # ── 5. Backfill: SnapshotStore organization_id ──────────────────────────────
    logger.info("Backfilling organization_id on form_snapshots...")
    result = db["form_snapshots"].update_many(
        {"organization_id": {"$exists": False}},
        {"$set": {"organization_id": ""}},
    )
    if result.modified_count:
        logger.info(f"  ✅ Backfilled {result.modified_count} snapshot docs with empty organization_id")
    else:
        logger.info("  ⏭  No backfill needed")

    # ── 6. users ────────────────────────────────────────────────────────────────
    logger.info("users collection:")
    _create_indexes(db["users"], [
        IndexModel(
            [("organization_id", ASCENDING), ("is_deleted", ASCENDING)],
            name="org_not_deleted",
        ),
        IndexModel(
            [("email", ASCENDING)],
            name="email_unique",
            unique=True,
            sparse=True,
        ),
    ], "users")

    logger.info("\n✅ Migration 001 complete")


if __name__ == "__main__":
    run()
