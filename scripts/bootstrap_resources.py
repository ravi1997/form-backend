#!/usr/bin/env python3
"""
Bootstrap script for form-backend.
Creates MongoDB indexes for the forms_db database.
Run inside the backend container: python scripts/bootstrap_resources.py
"""

import os
import sys
import time


def wait_for_mongo(uri: str, retries: int = 20, delay: int = 3):
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure

    for i in range(retries):
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=3000)
            client.admin.command("ping")
            print(f"✅ Connected to MongoDB: {uri}")
            return client
        except Exception as e:
            print(f"   Waiting for MongoDB ({i+1}/{retries})... {e}")
            time.sleep(delay)
    print("❌ Could not connect to MongoDB after multiple retries.")
    sys.exit(1)


def bootstrap():
    uri = os.environ.get("MONGODB_URI", "mongodb://shared-mongo:27017/forms_db")
    db_name = uri.rsplit("/", 1)[-1].split("?")[0]

    client = wait_for_mongo(uri)
    db = client[db_name]

    print(f"\n⚙️  Bootstrapping database: {db_name}")

    # forms collection
    try:
        db.forms.create_index("owner_id")
        db.forms.create_index("created_at")
        db.forms.create_index([("owner_id", 1), ("created_at", -1)])
        print("   ✅ forms: indexes created")
    except Exception as e:
        print(f"   ⚠️ forms indexes partially exist or failed: {e}")

    # submissions collection
    try:
        db.submissions.create_index("form_id")
        db.submissions.create_index("submitted_at")
        db.submissions.create_index([("form_id", 1), ("submitted_at", -1)])
        print("   ✅ submissions: indexes created")
    except Exception as e:
        print(f"   ⚠️ submissions indexes partially exist or failed: {e}")

    # users collection
    try:
        db.users.create_index("email", unique=True)
        db.users.create_index("created_at")
        print("   ✅ users: indexes created")
    except Exception as e:
        print(f"   ⚠️ users indexes partially exist or failed: {e}")

    client.close()
    print(f"\n✅ Bootstrap complete for {db_name}.\n")

    # ClickHouse bootstrap if configured
    from config.settings import settings
    if settings.OLAP_ENGINE == "clickhouse":
        print("⚙️  Bootstrapping ClickHouse database...")
        try:
            from clickhouse_driver import Client
            ch_client = Client.from_url(settings.CLICKHOUSE_URL)
            ch_client.execute(
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
            print("   ✅ ClickHouse: submission_analytics table created/verified")
        except Exception as e:
            print(f"   ⚠️ ClickHouse bootstrap failed: {e}")


if __name__ == "__main__":
    bootstrap()
