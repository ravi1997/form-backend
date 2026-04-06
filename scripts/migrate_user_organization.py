#!/usr/bin/env python3
"""
Migration script to ensure all users have an organization_id.
Sets users without an organization_id to a default organization.

Usage: python scripts/migrate_user_organization.py [--org-id <org_id>]
"""

import os
import sys
import argparse


def migrate_users(org_id="org_default"):
    """Update all users without organization_id to the specified org_id."""
    os.environ["APP_ENV"] = os.environ.get("APP_ENV", "development")

    from app import create_app
    from models.User import User
    from logger.unified_logger import app_logger, audit_logger

    app = create_app()

    with app.app_context():
        app_logger.info(f"Starting user organization migration to '{org_id}'")

        # Find all users without organization_id
        users_without_org = User.objects(organization_id=None)
        count = users_without_org.count()

        if count == 0:
            app_logger.info("No users without organization_id found")
            return

        app_logger.info(f"Found {count} users without organization_id")

        # Update each user
        for i, user in enumerate(users_without_org, 1):
            old_org_id = user.organization_id
            user.organization_id = org_id
            user.save()
            app_logger.info(
                f"[{i}/{count}] Updated user {user.email} (ID: {user.id}) - org: {old_org_id} -> {org_id}"
            )

        audit_logger.info(
            f"Migration complete: Updated {count} users to organization '{org_id}'"
        )
        app_logger.info(
            f"Migration complete: Updated {count} users to organization '{org_id}'"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate users to default organization"
    )
    parser.add_argument(
        "--org-id",
        default="org_default",
        help="Organization ID to assign (default: org_default)",
    )
    args = parser.parse_args()

    try:
        migrate_users(args.org_id)
        print(f"✅ Migration completed successfully")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
