"""
Migration script to identify and optionally fix legacy FormVersions missing snapshots.
"""
from models.Form import FormVersion, Form
from services.form_service import FormService
from mongoengine import connect
from config.settings import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def preflight_check():
    logger.info("Starting migration preflight check...")
    connect(host=settings.MONGODB_URI)
    
    legacy_versions = FormVersion.objects(snapshot__exists=False)
    count = legacy_versions.count()
    
    if count == 0:
        logger.info("No legacy FormVersions found. All versions have snapshots.")
        return
        
    logger.warning(f"Found {count} legacy FormVersions missing snapshots.")
    for fv in legacy_versions:
        logger.info(f"Legacy Version: {fv.id} for Form: {fv.form.id if fv.form else 'Unknown'}")

def migrate_missing_snapshots():
    logger.info("Starting snapshot migration...")
    connect(host=settings.MONGODB_URI)
    form_service = FormService()
    
    legacy_versions = FormVersion.objects(snapshot__exists=False)
    for fv in legacy_versions:
        try:
            if not fv.form:
                logger.error(f"FormVersion {fv.id} has no linked form. Skipping.")
                continue
                
            # Reconstruct snapshot from current sections if still relevant, 
            # or from the sections list if it was a reference list.
            # NOTE: This is a best-effort reconstruction.
            sections_data = []
            if fv.sections:
                for sec in fv.sections:
                    sections_data.append(form_service._snapshot_section(sec))
            
            if sections_data:
                fv.snapshot = {"sections": sections_data}
                fv.save()
                logger.info(f"Successfully migrated FormVersion {fv.id}")
            else:
                logger.warning(f"FormVersion {fv.id} has no sections to snapshot.")
                
        except Exception as e:
            logger.error(f"Failed to migrate FormVersion {fv.id}: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--migrate":
        migrate_missing_snapshots()
    else:
        preflight_check()
