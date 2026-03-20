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
    db.forms.create_index("owner_id")
    db.forms.create_index("created_at")
    db.forms.create_index([("owner_id", 1), ("created_at", -1)])
    print("   ✅ forms: indexes created")

    # submissions collection
    db.submissions.create_index("form_id")
    db.submissions.create_index("submitted_at")
    db.submissions.create_index([("form_id", 1), ("submitted_at", -1)])
    print("   ✅ submissions: indexes created")

    # users collection
    db.users.create_index("email", unique=True)
    db.users.create_index("created_at")
    print("   ✅ users: indexes created")

    client.close()
    print(f"\n✅ Bootstrap complete for {db_name}.\n")

if __name__ == "__main__":
    bootstrap()
