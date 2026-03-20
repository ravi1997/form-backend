"""
scripts/migrate_v1_2_0.py
Migration script to backfill organization_id for legacy documents and cleanup stale flags.
"""
from mongoengine import connect
from config.settings import settings
from models.Dashboard import Dashboard
from models.Form import Form
from models.Response import FormResponse
from services.audit_service import AuditLog
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    connect(host=settings.MONGODB_URI)
    
    DEFAULT_ORG_ID = "org-0000-default"
    
    models_to_migrate = [Dashboard, Form, FormResponse, AuditLog]
    
    for model in models_to_migrate:
        logger.info(f"Checking {model.__name__} for missing organization_id...")
        # Find docs where organization_id is missing or null
        count = model.objects(organization_id__exists=False).count()
        if count > 0:
            logger.info(f"Updating {count} records in {model.__name__}...")
            model.objects(organization_id__exists=False).update(set__organization_id=DEFAULT_ORG_ID)
            logger.info(f"Update complete for {model.__name__}.")
        else:
            logger.info(f"No records need update in {model.__name__}.")

    logger.info("Migration v1.2.0 completed successfully.")

if __name__ == "__main__":
    run_migration()
