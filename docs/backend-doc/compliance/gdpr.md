# GDPR Compliance

**Purpose:** Documentation for General Data Protection Regulation (GDPR) compliance guide.

**Scope:** Data subject rights, consent management, data portability, right to be forgotten, data retention, breach notification, privacy by design, and DPIA.

---

## Overview

This document outlines GDPR compliance requirements for the RIDP Form Platform, ensuring protection of personal data and adherence to EU data protection regulations.

**Target Audience:** Legal counsel, compliance officers, developers, data protection officers

---

## GDPR Principles

### Article 5 - Principles Relating to Processing of Personal Data

1. **Lawfulness, Fairness, and Transparency:** Data must be processed lawfully, fairly, and transparently
2. **Purpose Limitation:** Collected for specified, explicit, and legitimate purposes
3. **Data Minimization:** Adequate, relevant, and limited to what is necessary
4. **Accuracy:** Accurate and kept up to date
5. **Storage Limitation:** Kept no longer than necessary
6. **Integrity and Confidentiality:** Processed securely
7. **Accountability:** Controller responsible for compliance

---

## Data Subject Rights

### 1. Right to Access (Article 15)

**Implementation:**

```python
# routes/v1/compliance/gdpr_route.py
@bp.route("/compliance/gdpr/data-access", methods=["POST"])
@jwt_required()
def data_access_request():
    """Handle data subject access request."""
    user = get_current_user()

    # Collect all personal data
    personal_data = {
        "user_profile": {
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "address": user.address,
        },
        "form_responses": [],
        "audit_logs": [],
    }

    # Collect form responses
    responses = FormResponse.objects(
        submitted_by=user.id,
        is_deleted=False
    )

    for response in responses:
        personal_data["form_responses"].append({
            "form_id": str(response.form_id),
            "submitted_at": response.submitted_at,
            "data": redact_pii(response.data),
        })

    # Collect audit logs
    audit_logs = AuditLog.objects(
        user_id=user.id
    )

    for log in audit_logs:
        personal_data["audit_logs"].append({
            "timestamp": log.timestamp,
            "action": log.action,
            "resource": log.resource,
        })

    # Log access request
    audit_logger.info(
        f"GDPR data access request by user {user.email}"
    )

    # Return data to user
    return success_response(data=personal_data)
```

**Requirements:**
- Provide copy of personal data within 1 month
- Include purpose of processing
- Include categories of data
- Include recipients of data
- Include retention period
- Provide in structured, commonly used format

### 2. Right to Rectification (Article 16)

**Implementation:**

```python
@bp.route("/compliance/gdpr/rectify", methods=["POST"])
@jwt_required()
def rectify_data():
    """Handle data rectification request."""
    user = get_current_user()
    corrections = request.json.get("corrections", {})

    # Apply corrections
    if "name" in corrections:
        user.name = corrections["name"]
    if "email" in corrections:
        user.email = corrections["email"]
    if "phone" in corrections:
        user.phone = corrections["phone"]

    user.save()

    # Log rectification
    audit_logger.info(
        f"GDPR data rectification by user {user.email}: {corrections}"
    )

    return success_response(message="Data updated successfully")
```

### 3. Right to Erasure (Right to be Forgotten) (Article 17)

**Implementation:**

```python
@bp.route("/compliance/gdpr/erasure", methods=["POST"])
@jwt_required()
def request_erasure():
    """Handle right to be forgotten request."""
    user = get_current_user()

    # 1. Anonymize user data
    user.name = "Anonymous"
    user.email = f"deleted_{user.id}@deleted.com"
    user.phone = None
    user.address = None
    user.is_deleted = True
    user.deleted_at = datetime.utcnow()
    user.save()

    # 2. Soft-delete form responses
    FormResponse.objects(
        submitted_by=user.id
    ).update(set__is_deleted=True)

    # 3. Anonymize form response data
    responses = FormResponse.objects(submitted_by=user.id)
    for response in responses:
        response.data = anonymize_data(response.data)
        response.save()

    # 4. Delete files
    delete_user_files(user.id)

    # 5. Log erasure
    audit_logger.info(
        f"GDPR erasure request completed for user {user.email}"
    )

    return success_response(message="Data deleted successfully")
```

**Exceptions:**
- Legal obligation to retain data
- Public interest
- Scientific research
- Exercise of right of freedom of expression

### 4. Right to Restriction of Processing (Article 18)

**Implementation:**

```python
@bp.route("/compliance/gdpr/restrict", methods=["POST"])
@jwt_required()
def restrict_processing():
    """Restrict processing of personal data."""
    user = get_current_user()

    # Mark user as restricted
    user.processing_restricted = True
    user.restriction_reason = request.json.get("reason")
    user.save()

    # Log restriction
    audit_logger.info(
        f"GDPR processing restriction for user {user.email}: "
        f"{user.restriction_reason}"
    )

    return success_response(message="Processing restricted")
```

### 5. Right to Data Portability (Article 20)

**Implementation:**

```python
@bp.route("/compliance/gdpr/portability", methods=["POST"])
@jwt_required()
def data_portability():
    """Handle data portability request."""
    user = get_current_user()

    # Collect all data
    personal_data = collect_personal_data(user)

    # Create machine-readable format (JSON)
    export_data = json.dumps(personal_data, indent=2)

    # Create export file
    filename = f"data_export_{user.id}.json"
    filepath = f"/tmp/{filename}"

    with open(filepath, 'w') as f:
        f.write(export_data)

    # Log portability request
    audit_logger.info(
        f"GDPR data portability request by user {user.email}"
    )

    # Send file to user
    return send_file(
        filepath,
        mimetype='application/json',
        as_attachment=True,
        download_name=filename
    )
```

### 6. Right to Object (Article 21)

**Implementation:**

```python
@bp.route("/compliance/gdpr/object", methods=["POST"])
@jwt_required()
def object_processing():
    """Handle objection to processing."""
    user = get_current_user()
    objection = request.json.get("objection")

    # Record objection
    user.processing_objection = True
    user.objection_details = objection
    user.objection_date = datetime.utcnow()
    user.save()

    # Log objection
    audit_logger.warning(
        f"GDPR objection to processing by user {user.email}: {objection}"
    )

    # Stop processing (except for storage)
    if objection == "marketing":
        user.marketing_consent = False

    return success_response(message="Objection recorded")
```

---

## Consent Management

### Consent Recording

```python
# models/Consent.py
class Consent(Document):
    meta = {
        "collection": "consent_records",
        "queryset_class": TenantIsolatedSoftDeleteQuerySet,
    }

    user_id = StringField(required=True)
    organization_id = StringField(required=True)
    consent_type = StringField(required=True)  # marketing, analytics, terms
    consent_given = BooleanField(default=False)
    consent_date = DateTimeField(default=datetime.utcnow)
    consent_ip = StringField()
    revoked_date = DateTimeField()
    is_deleted = BooleanField(default=False)
```

### Consent Collection

```python
# routes/v1/auth_route.py
@bp.route("/register", methods=["POST"])
def register():
    # ... registration logic ...

    # Record consent
    consent = Consent(
        user_id=str(user.id),
        organization_id=user.organization_id,
        consent_type="terms",
        consent_given=True,
        consent_ip=request.remote_addr
    )
    consent.save()

    # Record marketing consent if given
    if request.json.get("marketing_consent"):
        marketing_consent = Consent(
            user_id=str(user.id),
            organization_id=user.organization_id,
            consent_type="marketing",
            consent_given=True,
            consent_ip=request.remote_addr
        )
        marketing_consent.save()

    return success_response(data={"user_id": str(user.id)})
```

### Consent Withdrawal

```python
@bp.route("/compliance/gdpr/consent/withdraw", methods=["POST"])
@jwt_required()
def withdraw_consent():
    """Withdraw consent."""
    user = get_current_user()
    consent_type = request.json.get("consent_type")

    # Update consent record
    Consent.objects(
        user_id=str(user.id),
        consent_type=consent_type
    ).update(
        set__consent_given=False,
        set__revoked_date=datetime.utcnow()
    )

    # Log withdrawal
    audit_logger.info(
        f"GDPR consent withdrawal by user {user.email}: {consent_type}"
    )

    return success_response(message="Consent withdrawn")
```

---

## Data Minimization

### Collection Principles

**Collect Only Necessary Data:**

```python
# CORRECT - Minimal data collection
class FormResponse(Document):
    form_id = StringField(required=True)
    submitted_by = StringField(required=True)
    submitted_at = DateTimeField(required=True)
    data = DictField()  # Only form fields defined in form schema

# WRONG - Excessive data collection
class FormResponse(Document):
    form_id = StringField(required=True)
    submitted_by = StringField(required=True)
    submitted_at = DateTimeField(required=True)
    data = DictField()
    ip_address = StringField()  # Not needed
    user_agent = StringField()  # Not needed
    device_info = DictField()  # Not needed
```

### Data Retention

**Retention Policy:**

```python
# config/settings.py
class Settings(BaseSettings):
    # Data retention periods
    FORM_RESPONSE_RETENTION_DAYS: int = 365  # 1 year
    USER_DATA_RETENTION_DAYS: int = 2555  # 7 years
    AUDIT_LOG_RETENTION_DAYS: int = 2555  # 7 years
    EXPORT_FILE_RETENTION_DAYS: int = 30  # 30 days
```

**Automatic Deletion:**

```python
# tasks/data_retention_tasks.py
@celery.task
def cleanup_expired_data():
    """Clean up expired data per GDPR requirements."""
    from datetime import timedelta

    # Delete old form responses
    cutoff_date = datetime.utcnow() - timedelta(
        days=settings.FORM_RESPONSE_RETENTION_DAYS
    )

    FormResponse.objects(
        created_at__lt=cutoff_date
    ).update(set__is_deleted=True)

    app_logger.info(
        f"Cleaned up form responses older than "
        f"{settings.FORM_RESPONSE_RETENTION_DAYS} days"
    )

    # Schedule to run daily
schedule.every().day.at("02:00").do(cleanup_expired_data)
```

---

## Data Protection by Design

### Default Privacy Settings

```python
# models/Form.py
class Form(Document):
    # Privacy settings
    is_public = BooleanField(default=False)  # Default: private
    require_consent = BooleanField(default=True)  # Default: require consent
    anonymize_responses = BooleanField(default=False)  # Optional: anonymize
    data_retention_days = IntField(default=365)  # Default: 1 year
```

### Privacy Impact Assessment (DPIA)

**DPIA Template:**

```python
# docs/compliance/dpia_template.md
# Data Protection Impact Assessment Template

1. PROCESSING DESCRIPTION
   - What personal data is being processed?
   - What is the purpose of processing?
   - Who has access to the data?

2. NECESSITY AND PROPORTIONALITY
   - Is the processing necessary for the purpose?
   - Is the data collected proportional to the purpose?
   - Can the purpose be achieved with less data?

3. RISKS TO RIGHTS AND FREEDOMS
   - What are the risks to data subjects?
   - Are there vulnerable individuals affected?
   - Could there be discrimination?

4. MITIGATION MEASURES
   - What security measures are in place?
   - How is consent obtained?
   - How is data minimization implemented?

5. COMPLIANCE WITH GDPR PRINCIPLES
   - Lawfulness, fairness, transparency
   - Purpose limitation
   - Data minimization
   - Accuracy
   - Storage limitation
   - Integrity and confidentiality
   - Accountability
```

---

## Data Breach Notification

### Breach Detection

```python
# utils/security_monitoring.py
def detect_data_breach():
    """Detect potential data breaches."""
    # Check for unusual activity
    suspicious_activities = [
        "unusual_data_export",
        "bulk_data_access",
        "unauthorized_access_attempt",
        "credential_theft"
    ]

    for activity in suspicious_activities:
        if detect_suspicious_activity(activity):
            trigger_breach_response(activity)

def trigger_breach_response(activity):
    """Trigger breach response procedures."""
    # 1. Log breach
    audit_logger.critical(
        f"Potential data breach detected: {activity}"
    )

    # 2. Notify security team
    send_alert_to_security_team(
        f"Potential data breach: {activity}",
        severity="P1"
    )

    # 3. Initiate incident response
    initiate_incident_response()
```

### Notification Timeline

**GDPR Article 33:**
- Notify supervisory authority within 72 hours of becoming aware
- Notify data subjects without undue delay if high risk

**Implementation:**

```python
# tasks/breach_notification_tasks.py
@celery.task
def notify_supervisory_authority(breach_details: dict):
    """Notify supervisory authority of data breach."""
    # Compile notification
    notification = {
        "nature_of_breach": breach_details["type"],
        "categories_of_data": breach_details["data_categories"],
        "affected_individuals": breach_details["affected_count"],
        "likely_consequences": breach_details["consequences"],
        "measures_taken": breach_details["mitigation"],
        "contact_person": breach_details["contact"]
    }

    # Send notification
    send_email(
        to="data.protection@authority.eu",
        subject=f"Data Breach Notification - {breach_details['incident_id']}",
        body=json.dumps(notification)
    )

@celery.task
def notify_data_subjects(breach_details: dict):
    """Notify affected data subjects."""
    for user_id in breach_details["affected_users"]:
        user = User.objects(id=user_id).first()

        # Notify user
        send_email(
            to=user.email,
            subject="Security Incident - Your Data May Have Been Affected",
            body=generate_breach_notification_email(user, breach_details)
        )

        # Log notification
        audit_logger.info(
            f"GDPR breach notification sent to user {user.email}"
        )
```

---

## Data Transfer

### International Data Transfers

**EU to Non-EU:**

```python
# config/settings.py
ALLOWED_DESTINATIONS = [
    "EU",  # European Union
    "EEA",  # European Economic Area
    "US",  # United States (with Privacy Shield)
    # Add other approved jurisdictions
]

def validate_data_transfer(destination: str) -> bool:
    """Validate data transfer to destination."""
    return destination in ALLOWED_DESTINATIONS
```

### Data Transfer Agreement

**Template:**

```
DATA PROCESSING AGREEMENT (GDPR)

1. PARTIES
   Data Controller: [Organization Name]
   Data Processor: [Service Provider]

2. SUBJECT MATTER
   Processing of personal data for form platform operations

3. DURATION
   This agreement is effective from [Date] until termination

4. NATURE AND PURPOSE
   Processing includes: storage, backup, analysis of personal data

5. DATA SUBJECTS
   Categories of data subjects: form users, form respondents

6. PERSONAL DATA
   Categories of personal data: names, emails, addresses, form responses

7. OBLIGATIONS OF PROCESSOR
   - Process data only on controller's instructions
   - Ensure confidentiality and security
   - Assist with data subject rights
   - Assist with breach notification
   - Return or delete data after termination

8. SECURITY MEASURES
   [List security measures]

9. SUBPROCESSORS
   [List approved subprocessors]

10. DATA PROTECTION OFFICER
    [Contact information]
```

---

## Privacy Controls

### Access Controls

**Role-Based Access Control:**

```python
# utils/security_helpers.py
def check_data_access_permission(user: User, data_type: str) -> bool:
    """Check if user has permission to access data type."""
    # Only data protection officers can access all data
    if user.role in ["admin", "superadmin"]:
        return True

    # Users can only access their own data
    if data_type == "personal_data":
        return True

    # Other access requires explicit consent
    return False
```

### Audit Logging

```python
# All personal data access must be logged
audit_logger.info(
    f"Personal data access: user={user.email}, "
    f"data_type={data_type}, action={action}"
)
```

---

## Compliance Checklist

### GDPR Compliance Checklist

- [ ] Legal basis for processing identified (consent, contract, legitimate interest)
- [ ] Privacy policy published and accessible
- [ ] Consent obtained and recorded
- [ ] Data subject rights implemented
- [ ] Data minimization implemented
- [ ] Data retention policy defined and enforced
- [ ] Data security measures implemented
- [ ] Data breach notification procedures established
- [ ] Data protection impact assessments completed
- [ ] Data protection officer appointed (if required)
- [ ] Data transfer agreements in place
- [ ] Privacy by design principles followed
- [ ] Accountability measures implemented
- [ ] Regular audits and reviews scheduled
- [ ] Staff training on GDPR completed

---

## References

- [GDPR Text](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679)
- [UK ICO GDPR Guide](https://ico.org.uk/for-organisations/guide-to-data-protection/guide-to-the-general-data-protection-regulation-gdpr/)
- [European Data Protection Board](https://edpb.europa.eu/)
- [GDPR Compliance Checklist](https://gdpr.eu/checklist/)
- [Data Protection Impact Assessment Template](https://ico.org.uk/for-organisations/data-protection/by-design/data-protection-impact-assessments/)
