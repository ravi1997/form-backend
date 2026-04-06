# Data Retention Policy

**Purpose:** Documentation for unified data retention policy across all data types.

**Scope:** Form response retention, user data retention, translation job retention, export file retention, audit log retention, and automated deletion policies.

---

## Overview

This document outlines the data retention policies for the RIDP Form Platform, ensuring compliance with GDPR, HIPAA, and other regulatory requirements while balancing business needs with privacy principles.

**Target Audience:** Compliance officers, data protection officers, database administrators, developers

---

## Retention Principles

### Data Minimization

**Principle:** Retain data only as long as necessary for the purpose for which it was collected.

### Purpose-Based Retention

**Data is retained based on its purpose:**

| Data Type | Purpose | Retention Period | Legal Basis |
|-----------|---------|-----------------|-------------|
| User profiles | Authentication, authorization | Account lifetime + 7 years | Legitimate interest |
| Form responses | Form functionality, analytics | 1 year (configurable) | Contract, legitimate interest |
| Audit logs | Compliance, security | 7 years | Legal obligation |
| Export files | Temporary data transfer | 30 days | Legitimate interest |
| Translation jobs | AI features | 90 days | Legitimate interest |
| Analytics data | Business intelligence | 2 years | Legitimate interest |

---

## Form Response Retention

### Retention Policy

**Default Retention:** 1 year after submission

**Configuration:**

```python
# config/settings.py
class Settings(BaseSettings):
    # Data retention periods
    FORM_RESPONSE_RETENTION_DAYS: int = Field(default=365, ge=30, le=2555)
```

### Per-Form Retention

**Form-level configuration:**

```python
# models/Form.py
class Form(Document):
    # ... existing fields ...

    # Data retention
    data_retention_days = IntField(default=365)  # Configurable per form
    data_retention_policy = StringField(
        default="fixed_period",
        choices=["fixed_period", "indefinite", "manual"]
    )
```

### Automated Deletion

```python
# tasks/data_retention_tasks.py
@celery.task
def cleanup_expired_form_responses():
    """Clean up expired form responses."""
    from datetime import timedelta

    # Get all forms with retention policies
    forms = Form.objects(is_deleted=False)

    for form in forms:
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(
            days=form.data_retention_days
        )

        # Delete expired responses
        expired_count = FormResponse.objects(
            form_id=form.id,
            created_at__lt=cutoff_date
        ).update(set__is_deleted=True)

        if expired_count > 0:
            app_logger.info(
                f"Deleted {expired_count} expired responses for form {form.id}"
            )

            audit_logger.info(
                f"Data retention: Deleted {expired_count} responses "
                f"for form {form.id} (retention: {form.data_retention_days} days)"
            )

# Schedule daily
schedule.every().day.at("02:00").do(cleanup_expired_form_responses)
```

### Manual Deletion

**User-initiated deletion:**

```python
@bp.route("/forms/<form_id>/responses/delete", methods=["POST"])
@jwt_required()
def delete_all_responses(form_id):
    """Delete all responses for a form."""
    user = get_current_user()
    form = Form.objects.get(id=form_id, organization_id=user.organization_id)

    # Require confirmation
    confirm = request.json.get("confirm")
    if confirm != "DELETE_ALL":
        return error_response(
            message="Confirmation required. Send {\"confirm\": \"DELETE_ALL\"}",
            status_code=400
        )

    # Count responses
    response_count = FormResponse.objects(form_id=form_id).count()

    # Soft delete
    FormResponse.objects(form_id=form_id).update(set__is_deleted=True)

    # Log deletion
    audit_logger.info(
        f"Manual deletion of {response_count} responses "
        f"for form {form_id} by user {user.email}"
    )

    return success_response(
        message=f"Deleted {response_count} responses",
        data={"deleted_count": response_count}
    )
```

---

## User Data Retention

### User Account Retention

**Retention Period:** Account lifetime + 7 years after account deletion

**User Data Types:**

| Data Type | Retention | Notes |
|-----------|-----------|-------|
| Profile information | Account lifetime + 7 years | Name, email, phone |
| Authentication data | Account lifetime + 7 years | Password hashes, tokens |
| Audit logs | 7 years | All user actions |
| Form submissions | Per-form retention | Follows form retention policy |
| Uploaded files | Per-form retention | Deleted with form responses |

### Account Deletion

**Soft Delete:**

```python
# routes/v1/user_route.py
@bp.route("/user/account", methods=["DELETE"])
@jwt_required()
def delete_account():
    """Delete user account."""
    user = get_current_user()

    # Soft delete user account
    user.is_deleted = True
    user.deleted_at = datetime.utcnow()
    user.email = f"deleted_{user.id}@deleted.com"
    user.save()

    # Log deletion
    audit_logger.info(
        f"User account deleted: {user.email} "
        f"(retention: 7 years from deletion date)"
    )

    # Revoke all sessions
    revoke_all_user_sessions(user)

    return success_response(message="Account deleted")
```

**Data Anonymization (Future):**

```python
# tasks/anonymization_tasks.py
@celery.task
def anonymize_expired_user_data():
    """Anonymize user data after retention period."""
    from datetime import timedelta

    # Find users deleted 7 years ago
    cutoff_date = datetime.utcnow() - timedelta(days=7*365)

    expired_users = User.objects(
        is_deleted=True,
        deleted_at__lt=cutoff_date
    )

    for user in expired_users:
        # Anonymize all user data
        user.name = "Anonymous"
        user.phone = None
        user.address = None
        user.save()

        # Anonymize form responses
        FormResponse.objects(
            submitted_by=user.id
        ).update(set__data={"anonymized": True})

    app_logger.info(
        f"Anonymized {len(expired_users)} expired user accounts"
    )
```

---

## Translation Job Retention

### Retention Policy

**Retention Period:** 90 days after job completion

**Rationale:**
- Translation jobs are temporary artifacts
- Results are stored in final form
- Retention for debugging and review

**Automated Deletion:**

```python
# tasks/translation_cleanup.py
@celery.task
def cleanup_expired_translation_jobs():
    """Clean up expired translation jobs."""
    from datetime import timedelta

    # Calculate cutoff date
    cutoff_date = datetime.utcnow() - timedelta(days=90)

    # Delete expired jobs (hard delete - documented exception)
    deleted_count = TranslationJob.objects(
        status="completed",
        completed_at__lt=cutoff_date
    ).delete()

    if deleted_count > 0:
        app_logger.info(
            f"Deleted {deleted_count} expired translation jobs"
        )

        audit_logger.info(
            f"Data retention: Deleted {deleted_count} translation jobs "
            f"(retention: 90 days)"
        )

# Schedule daily
schedule.every().day.at("03:00").do(cleanup_expired_translation_jobs)
```

---

## Export File Retention

### Retention Policy

**Retention Period:** 30 days after export generation

**Rationale:**
- Export files are temporary
- Users should download and store locally
- Reduce storage costs

**Automated Deletion:**

```python
# tasks/export_cleanup.py
@celery.task
def cleanup_expired_export_files():
    """Clean up expired export files."""
    import os
    from datetime import timedelta

    # Calculate cutoff date
    cutoff_date = datetime.utcnow() - timedelta(days=30)

    # Find expired export records
    expired_exports = ExportJob.objects(
        status="completed",
        created_at__lt=cutoff_date
    )

    for export in expired_exports:
        # Delete file if exists
        if export.filepath and os.path.exists(export.filepath):
            os.remove(export.filepath)

        # Soft delete record
        export.is_deleted = True
        export.save()

    app_logger.info(
        f"Cleaned up {len(expired_exports)} expired export files"
    )
```

---

## Audit Log Retention

### Retention Policy

**Retention Period:** 7 years (GDPR requirement)

**Rationale:**
- GDPR requires audit logs for accountability
- HIPAA requires 6 years
- 7 years covers both requirements

**Log Types:**

| Log Type | Retention | Purpose |
|-----------|-----------|---------|
| Access logs | 7 years | Authentication, authorization |
| Data access logs | 7 years | PHI/PII access |
| Data change logs | 7 years | Create, update, delete |
| Security logs | 7 years | WAF blocks, rate limits |
| Error logs | 90 days | Debugging, error analysis |
| Debug logs | 30 days | Troubleshooting |

**Automated Deletion:**

```python
# tasks/audit_log_cleanup.py
@celery.task
def cleanup_expired_audit_logs():
    """Clean up expired audit logs."""
    from datetime import timedelta

    # Calculate cutoff date
    cutoff_date = datetime.utcnow() - timedelta(days=7*365)

    # Delete logs older than 7 years
    # Note: This depends on your log storage solution
    # For MongoDB-stored logs:
    deleted_count = AuditLog.objects(
        timestamp__lt=cutoff_date
    ).delete()

    if deleted_count > 0:
        app_logger.info(
            f"Deleted {deleted_count} expired audit log records "
            f"(retention: 7 years)"
        )

    # For file-based logs:
    cleanup_log_files("/var/log/audit/", cutoff_date)

# Schedule weekly
schedule.every().week.do(cleanup_expired_audit_logs)
```

### Audit Log Archival

**Archive old logs before deletion:**

```python
# tasks/audit_log_archival.py
@celery.task
def archive_audit_logs():
    """Archive audit logs before deletion."""
    from datetime import timedelta

    # Calculate cutoff dates
    archive_cutoff = datetime.utcnow() - timedelta(days=365)  # 1 year old
    delete_cutoff = datetime.utcnow() - timedelta(days=7*365)  # 7 years old

    # Archive logs between 1 and 7 years old
    logs_to_archive = AuditLog.objects(
        timestamp__gte=archive_cutoff,
        timestamp__lt=delete_cutoff
    )

    # Export to compressed archive
    archive_file = f"/var/log/audit/archive_{datetime.utcnow().strftime('%Y%m%d')}.tar.gz"
    with tarfile.open(archive_file, "w:gz") as tar:
        for log in logs_to_archive:
            # Add to archive
            # (implementation depends on log format)
            pass

    # Upload to cold storage (S3 Glacier)
    upload_to_glacier(archive_file)

    app_logger.info(
        f"Archived {len(logs_to_archive)} audit log records"
    )
```

---

## Backup Retention

### Backup Retention Policy

| Backup Type | Retention | Location |
|-------------|-----------|----------|
| Daily full backups | 30 days | Local + Cloud |
| Weekly backups | 3 months | Local + Cloud |
| Monthly backups | 1 year | Cloud only |
| Quarterly backups | 7 years | Cloud (Glacier) |

### Backup Cleanup

```python
# tasks/backup_cleanup.py
@celery.task
def cleanup_expired_backups():
    """Clean up expired backups."""
    # Daily backups: keep 30 days
    cleanup_backups(pattern="mongodb_daily_*", days=30)

    # Weekly backups: keep 3 months
    cleanup_backups(pattern="mongodb_weekly_*", days=90)

    # Monthly backups: keep 1 year
    cleanup_backups(pattern="mongodb_monthly_*", days=365)

def cleanup_backups(pattern: str, days: int):
    """Clean up backups matching pattern."""
    import os
    from datetime import timedelta

    backup_dir = "/backups/mongodb"
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    for backup in os.listdir(backup_dir):
        if backup.startswith(pattern):
            backup_path = os.path.join(backup_dir, backup)
            backup_date = extract_date_from_filename(backup)

            if backup_date < cutoff_date:
                os.remove(backup_path)

                app_logger.info(
                    f"Deleted expired backup: {backup}"
                )
```

---

## Data Retention by Compliance Framework

### GDPR Retention Requirements

| Data Type | Minimum Retention | Maximum Retention | Notes |
|-----------|------------------|------------------|-------|
| Personal data | As long as necessary | Not indefinite | Purpose limitation |
| Consent records | 2 years after withdrawal | Indefinite | Legal requirement |
| Access logs | 7 years | 7 years | Accountability |
| Breach records | 7 years | 7 years | Article 33 |

### HIPAA Retention Requirements

| Data Type | Minimum Retention | Notes |
|-----------|------------------|-------|
| PHI | 6 years | Security Rule |
| Audit logs | 6 years | Security Rule |
| Training records | 6 years | Security Rule |
| Security policies | 6 years | Security Rule |

---

## Data Retention Exceptions

### Legal Holds

**Purpose:** Prevent deletion when litigation is pending.

**Implementation:**

```python
# models/LegalHold.py
class LegalHold(Document):
    meta = {
        "collection": "legal_holds",
        "queryset_class": TenantIsolatedSoftDeleteQuerySet,
    }

    case_id = StringField(required=True)
    description = StringField()
    scope = StringField(choices=["all", "form", "user"])
    scope_id = StringField()
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    released_at = DateTimeField()

# Check for legal holds before deletion
def check_legal_holds(data_id: str, data_type: str) -> bool:
    """Check if data is under legal hold."""
    holds = LegalHold.objects(
        is_active=True,
        scope=data_type,
        scope_id=data_id
    )

    return holds.count() > 0
```

### Regulatory Requirements

**Extended Retention:**

```python
# models/RegulatoryRetention.py
class RegulatoryRetention(Document):
    meta = {
        "collection": "regulatory_retention",
        "queryset_class": TenantIsolatedSoftDeleteQuerySet,
    }

    regulation = StringField(required=True)  # GDPR, HIPAA, SOX, etc.
    data_type = StringField(required=True)
    extended_retention_days = IntField(required=True)
    reason = StringField()
    is_active = BooleanField(default=True)
```

---

## Data Retention Reports

### Monthly Retention Report

```python
# tasks/retention_reports.py
@celery.task
def generate_retention_report():
    """Generate monthly data retention report."""
    from datetime import timedelta, datetime

    # Get retention statistics
    report = {
        "report_date": datetime.utcnow().isoformat(),
        "report_period": "monthly",
        "statistics": {
            "form_responses": {
                "total": FormResponse.objects(is_deleted=False).count(),
                "retained": FormResponse.objects(is_deleted=False, created_at__gte=datetime.utcnow() - timedelta(days=365)).count(),
                "expired": FormResponse.objects(is_deleted=True, created_at__lt=datetime.utcnow() - timedelta(days=365)).count(),
            },
            "users": {
                "total": User.objects(is_deleted=False).count(),
                "deleted": User.objects(is_deleted=True).count(),
            },
            "audit_logs": {
                "total": AuditLog.objects(timestamp__gte=datetime.utcnow() - timedelta(days=30)).count(),
                "archived": get_archived_log_count(),
            },
        },
        "compliance": {
            "gdpr": check_gdpr_compliance(),
            "hipaa": check_hipaa_compliance(),
        },
    }

    # Save report
    report_file = f"/var/log/reports/retention_{datetime.utcnow().strftime('%Y%m')}.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)

    # Send to compliance officer
    send_retention_report(report)

    app_logger.info("Generated monthly retention report")

# Schedule monthly
schedule.every().month.do(generate_retention_report)
```

---

## Configuration Reference

### Retention Settings

```python
# config/settings.py
class Settings(BaseSettings):
    # Data retention periods
    FORM_RESPONSE_RETENTION_DAYS: int = Field(default=365, ge=30, le=2555)
    USER_DATA_RETENTION_DAYS: int = Field(default=2555, ge=30, le=3650)  # 7 years
    TRANSLATION_JOB_RETENTION_DAYS: int = Field(default=90, ge=30, le=365)
    EXPORT_FILE_RETENTION_DAYS: int = Field(default=30, ge=7, le=90)
    AUDIT_LOG_RETENTION_DAYS: int = Field(default=2555, ge=30, le=3650)  # 7 years
    ERROR_LOG_RETENTION_DAYS: int = Field(default=90, ge=7, le=365)
    DEBUG_LOG_RETENTION_DAYS: int = Field(default=30, ge=7, le=90)

    # Backup retention
    BACKUP_DAILY_RETENTION_DAYS: int = 30
    BACKUP_WEEKLY_RETENTION_DAYS: int = 90
    BACKUP_MONTHLY_RETENTION_DAYS: int = 365
    BACKUP_QUARTERLY_RETENTION_DAYS: int = 2555  # 7 years
```

---

## Best Practices

### 1. Define Clear Retention Policies

```python
# CORRECT - Clear policies
FORM_RESPONSE_RETENTION_DAYS = 365  # 1 year
USER_DATA_RETENTION_DAYS = 2555  # 7 years

# WRONG - No clear policy
# Keep data indefinitely
```

### 2. Automate Deletion

```python
# CORRECT - Automated deletion
schedule.every().day.at("02:00").do(cleanup_expired_data)

# WRONG - Manual deletion
# Relies on human to delete data
```

### 3. Archive Before Deletion

```python
# CORRECT - Archive first
archive_expired_data()
then_delete_expired_data()

# WRONG - Delete without archival
# Data lost forever
```

### 4. Audit All Deletions

```python
# CORRECT - Log all deletions
audit_logger.info(
    f"Deleted {count} records (reason: retention_expired)"
)

# WRONG - No logging
# No audit trail
```

### 5. Respect Legal Holds

```python
# CORRECT - Check legal holds
if check_legal_holds(data_id, data_type):
    skip_deletion(data_id)

# WRONG - Delete regardless
# May violate legal obligations
```

---

## References

- [GDPR Article 5(1)(e) - Storage Limitation](https://gdpr-info.eu/art-5-gdpr/)
- [HIPAA Security Rule §164.312(a)(2)(i) - Automatic Logoff](https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/)
- [NIST SP 800-53: AU-11 - Audit Record Retention](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
- [ISO 27001 - Retention of Information](https://www.iso.org/standard/27001)
