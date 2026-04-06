# HIPAA Compliance

**Purpose:** Documentation for Health Insurance Portability and Accountability Act (HIPAA) compliance guide.

**Scope:** PHI identification and classification, minimum necessary disclosure, access controls, audit controls, integrity controls, transmission security, and workforce training.

---

## Overview

This document outlines HIPAA compliance requirements for the RIDP Form Platform when handling Protected Health Information (PHI). It covers PHI identification, security controls, and administrative requirements.

**Target Audience:** Compliance officers, security officers, developers, healthcare data handlers

---

## HIPAA Overview

### HIPAA Rules

1. **Privacy Rule (45 CFR Part 160 and 164 Subparts A and E):** Protects individuals' PHI
2. **Security Rule (45 CFR Part 164 Subparts A and C):** Protects electronic PHI (ePHI)
3. **Breach Notification Rule (45 CFR Part 164 Subparts D):** Requires notification of breaches
4. **Enforcement Rule (45 CFR Part 160 Subparts C, D, and E):** Penalties for non-compliance

---

## PHI Identification and Classification

### What is PHI?

**Protected Health Information (PHI)** is individually identifiable health information transmitted or maintained in any form or medium, including:

- Names
- Geographic identifiers smaller than a state (except for initial 3 digits of zip code)
- Elements of dates (dates of birth, admission, discharge, death) directly related to an individual
- Telephone numbers
- Fax numbers
- Email addresses
- Social Security numbers
- Medical record numbers
- Health plan beneficiary numbers
- Account numbers
- Certificate/license numbers
- Vehicle identifiers
- Device identifiers
- Web Universal Resource Locators (URLs)
- Internet Protocol (IP) address numbers
- Biometric identifiers (fingerprints, voiceprints)
- Full-face photographic images
- Any other unique identifying number, characteristic, or code

### PHI Classification

```python
# utils/phi_classifier.py
class PHIClassifier:
    """Classify data as PHI or non-PHI."""

    PHI_FIELDS = {
        "name", "first_name", "last_name",
        "date_of_birth", "dob", "birth_date",
        "address", "street", "city", "state", "zip",
        "phone", "telephone", "mobile",
        "email",
        "ssn", "social_security_number",
        "medical_record_number", "mrn",
        "health_plan_number", "insurance_number",
        "account_number",
    }

    @classmethod
    def is_phi(cls, field_name: str) -> bool:
        """Check if field contains PHI."""
        return field_name.lower() in cls.PHI_FIELDS

    @classmethod
    def classify_data(cls, data: dict) -> dict:
        """Classify data as PHI or non-PHI."""
        classified = {}

        for key, value in data.items():
            if cls.is_phi(key):
                classified[key] = {
                    "value": value,
                    "is_phi": True,
                    "sensitivity": "high"
                }
            else:
                classified[key] = {
                    "value": value,
                    "is_phi": False,
                    "sensitivity": "low"
                }

        return classified
```

### PHI Handling Policies

**Data Collection:**

```python
# When collecting PHI
def collect_phi(data: dict):
    """Collect PHI with proper consent."""
    # Verify consent is obtained
    if not data.get("phi_consent"):
        raise ValueError("PHI consent required")

    # Classify data
    classified_data = PHIClassifier.classify_data(data)

    # Store PHI with appropriate security
    phi_data = {
        k: v for k, v in classified_data.items() if v["is_phi"]
    }

    # Encrypt PHI
    encrypted_phi = encrypt_phi(phi_data)

    # Log PHI access
    audit_logger.info(
        f"PHI collected: fields={list(phi_data.keys())}"
    )

    return encrypted_phi
```

---

## Minimum Necessary Standard

### Minimum Necessary Disclosure

**Requirement:** Use or disclose only the minimum necessary PHI to accomplish the intended purpose.

**Implementation:**

```python
# utils/phi_minimization.py
def minimize_phi(requested_fields: list, available_phi: dict) -> dict:
    """Apply minimum necessary standard."""
    # Only include requested fields
    minimized = {}

    for field in requested_fields:
        if field in available_phi:
            # Apply additional filtering if possible
            if field == "date_of_birth":
                # Only year if that's sufficient
                if request.purpose == "age_verification":
                    minimized[field] = extract_year(available_phi[field])
                else:
                    minimized[field] = available_phi[field]
            else:
                minimized[field] = available_phi[field]

    # Log PHI disclosure
    audit_logger.info(
        f"PHI disclosed: fields={list(minimized.keys())}, "
        f"purpose={request.purpose}"
    )

    return minimized
```

### Role-Based Access to PHI

```python
# models/Role.py
class Role(Document):
    name = StringField(required=True)
    phi_access_level = StringField(choices=[
        "none",           # No PHI access
        "demographics",   # Name, DOB only
        "limited",        # Limited PHI
        "full",           # All PHI
    ])
```

---

## Access Controls

### Unique User Identification

**Requirement:** Assign unique name and/or number for identifying and tracking user identity.

**Implementation:**

```python
# models/User.py
class User(Document):
    # Unique identifiers
    user_id = StringField(required=True, unique=True)  # Internal ID
    username = StringField(required=True, unique=True)   # Login ID
    email = StringField(required=True, unique=True)     # Email ID

    # PHI access
    phi_access_level = StringField(default="none")
```

### Emergency Access Procedure

**Emergency Access:**

```python
# routes/v1/emergency_route.py
@bp.route("/emergency/phi-access", methods=["POST"])
@require_roles("superadmin")
def emergency_phi_access():
    """Handle emergency access to PHI."""
    access_request = request.json

    # Verify emergency access criteria
    if not verify_emergency_criteria(access_request):
        return error_response(
            message="Emergency access criteria not met",
            status_code=403
        )

    # Grant emergency access
    access_code = generate_emergency_access_code()
    user = User.objects(id=access_request["user_id"]).first()
    user.emergency_access_code = access_code
    user.emergency_access_expires = datetime.utcnow() + timedelta(hours=24)
    user.save()

    # Log emergency access
    audit_logger.warning(
        f"Emergency PHI access granted for user {user.email} "
        f"by admin {get_current_user().email}"
    )

    return success_response(data={"access_code": access_code})
```

### Access Authorization

```python
# utils/phi_access_control.py
def authorize_phi_access(user: User, resource: str, action: str) -> bool:
    """Authorize user to access PHI resource."""
    # Check user's PHI access level
    phi_level = user.phi_access_level

    # Define access matrix
    access_matrix = {
        "none": [],
        "demographics": ["view_demographics"],
        "limited": ["view_demographics", "view_limited_phi"],
        "full": ["view_demographics", "view_limited_phi", "view_all_phi"],
    }

    # Check if action is authorized
    return action in access_matrix.get(phi_level, [])
```

---

## Audit Controls

### Audit Log Requirements

**What to Log:**

```python
# All PHI access must be logged
def log_phi_access(user: User, phi_fields: list, action: str):
    """Log PHI access."""
    audit_logger.info(
        f"PHI access: user={user.email}, "
        f"fields={phi_fields}, action={action}, "
        f"timestamp={datetime.utcnow()}, "
        f"ip_address={request.remote_addr}"
    )
```

### Audit Log Retention

**Requirement:** Retain audit logs for 6 years.

```python
# config/settings.py
class Settings(BaseSettings):
    # HIPAA audit log retention
    AUDIT_LOG_RETENTION_DAYS: int = 6 * 365  # 6 years
```

### Audit Log Security

```python
# Protect audit logs
def secure_audit_logs():
    """Ensure audit logs are protected."""
    # 1. Write to secure storage
    secure_storage = "/var/log/audit/secure/"

    # 2. Encrypt logs
    encryption_key = get_encryption_key()
    encrypt_logs_in_directory(secure_storage, encryption_key)

    # 3. Restrict access
    os.chmod(secure_storage, 0o700)

    # 4. Monitor access to audit logs
    monitor_audit_log_access(secure_storage)
```

---

## Integrity Controls

### Data Integrity

**Mechanisms:**

1. **Digital Signatures:**
```python
# utils/phi_integrity.py
def sign_phi_data(data: dict) -> str:
    """Digitally sign PHI data."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    private_key = load_private_key()

    signature = private_key.sign(
        json.dumps(data).encode(),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )

    return signature.hex()

def verify_phi_signature(data: dict, signature: str) -> bool:
    """Verify PHI data signature."""
    public_key = load_public_key()

    try:
        public_key.verify(
            bytes.fromhex(signature),
            json.dumps(data).encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True
    except Exception:
        return False
```

2. **Checksum Validation:**
```python
def verify_phi_integrity(phi_data: dict, checksum: str) -> bool:
    """Verify PHI data integrity using checksum."""
    calculated_checksum = calculate_checksum(phi_data)

    return calculated_checksum == checksum
```

### Change Logging

**Track all changes to PHI:**

```python
# models/PHIChangeLog.py
class PHIChangeLog(Document):
    meta = {
        "collection": "phi_change_log",
        "queryset_class": TenantIsolatedSoftDeleteQuerySet,
    }

    user_id = StringField(required=True)
    organization_id = StringField(required=True)
    phi_record_id = StringField(required=True)
    phi_record_type = StringField(required=True)  # user, response, etc.
    changed_fields = ListField(StringField())
    previous_values = DictField()
    new_values = DictField()
    changed_by = StringField(required=True)
    change_reason = StringField()
    timestamp = DateTimeField(default=datetime.utcnow)
    is_deleted = BooleanField(default=False)
```

---

## Transmission Security

### Encryption Requirements

**At Rest:**

```python
# Encrypt PHI at rest
def encrypt_phi(data: dict) -> str:
    """Encrypt PHI data at rest."""
    from cryptography.fernet import Fernet

    key = load_encryption_key()
    cipher_suite = Fernet(key)

    encrypted_data = cipher_suite.encrypt(json.dumps(data).encode())

    return encrypted_data.decode()

# Decrypt PHI
def decrypt_phi(encrypted_data: str) -> dict:
    """Decrypt PHI data at rest."""
    from cryptography.fernet import Fernet

    key = load_encryption_key()
    cipher_suite = Fernet(key)

    decrypted_data = cipher_suite.decrypt(encrypted_data.encode())

    return json.loads(decrypted_data.decode())
```

**In Transit:**

```python
# Ensure all PHI is transmitted over TLS/SSL
# Configuration in nginx/https setup
ssl_protocols = ["TLSv1.2", "TLSv1.3"]
ssl_ciphers = "HIGH:!aNULL:!MD5:!3DES"
```

### Secure Transmission

**API Requirements:**

```python
# routes/v1/phi_route.py
@bp.route("/phi/<resource_id>", methods=["GET"])
@jwt_required()
def get_phi(resource_id):
    """Get PHI with secure transmission."""
    user = get_current_user()

    # Verify PHI access
    if not authorize_phi_access(user, resource_id, "view"):
        return error_response(
            message="PHI access denied",
            status_code=403
        )

    # Get PHI data
    phi_data = get_phi_data(resource_id)

    # Encrypt PHI for transmission
    encrypted_phi = encrypt_phi(phi_data)

    # Log PHI access
    log_phi_access(user, phi_data.keys(), "view")

    return success_response(data={"encrypted_phi": encrypted_phi})
```

---

## Workforce Training

### Training Requirements

**Initial Training:**
- All workforce members must complete HIPAA training within 90 days of hire
- Training must cover Privacy Rule, Security Rule, and Breach Notification Rule

**Annual Refresher:**
- All workforce members must complete annual refresher training

**Documentation:**
- Training completion must be documented and retained for 6 years

### Training Topics

1. **Privacy Rule:**
   - What is PHI
   - Minimum necessary standard
   - Uses and disclosures of PHI
   - Patient rights

2. **Security Rule:**
   - Administrative safeguards
   - Physical safeguards
   - Technical safeguards

3. **Breach Notification:**
   - What constitutes a breach
   - Breach notification timeline
   - Documentation requirements

4. **Policies and Procedures:**
   - Access control policies
   - PHI handling procedures
   - Incident response procedures

---

## Business Associate Agreements

### BAAs Required

**When to Use BAA:**
- External cloud providers (AWS, Azure, GCP)
- Third-party services (analytics, backup)
- Vendors who access PHI
- Subcontractors

### BAA Template

```
BUSINESS ASSOCIATE AGREEMENT (HIPAA)

1. PARTIES
   Covered Entity: [Organization Name]
   Business Associate: [Vendor Name]

2. PERMITTED USES AND DISCLOSURES
   Business Associate may use or disclose PHI only as permitted:
   - To perform services for Covered Entity
   - As required by law
   - For Covered Entity's management or administration

3. OBLIGATIONS OF BUSINESS ASSOCIATE
   - Implement appropriate safeguards
   - Not use or disclose PHI except as permitted
   - Report security incidents
   - Ensure compliance with Privacy Rule
   - Make PHI available to Covered Entity

4. SECURITY SAFEGUARDS
   - Administrative safeguards
   - Physical safeguards
   - Technical safeguards

5. TERM AND TERMINATION
   - This agreement is effective from [Date]
   - Upon termination, Business Associate must:
     * Return or destroy PHI
     * Provide certification of destruction

6. MISUSE OF PHI
   - Business Associate reports any misuse to Covered Entity
   - Covered Entity has right to terminate agreement
```

---

## Breach Notification

### Breach Assessment

**Determine if breach:**

```python
# utils/breach_assessment.py
def assess_phi_breach(incident: dict) -> bool:
    """Assess if incident is a PHI breach."""
    # 1. Check if PHI was accessed
    phi_exposed = incident.get("phi_exposed", False)

    if not phi_exposed:
        return False

    # 2. Check if PHI was compromised
    phi_compromised = incident.get("phi_compromised", False)

    if not phi_compromised:
        return False

    # 3. Check if low probability of compromise
    low_probability = assess_compromise_probability(incident)

    if low_probability:
        return False

    # 4. Otherwise, it's a breach
    return True
```

### Notification Requirements

**Timeline:**
- Notify affected individuals without unreasonable delay (no later than 60 days)
- Notify HHS (Department of Health and Human Services)
   - If < 500 affected: Within 60 days
   - If ≥ 500 affected: Within 60 days and HHS website notice

**Notification Content:**
```python
def generate_breach_notification(incident: dict) -> dict:
    """Generate breach notification."""
    return {
        "description_of_breach": incident["description"],
        "types_of_phi": incident["phi_types"],
        "steps_to_take": [
            "Monitor financial accounts",
            "Place fraud alert on credit file",
            "Change passwords"
        ],
        "contact_information": {
            "phone": "1-800-XXX-XXXX",
            "email": "privacy@example.com",
            "website": "https://example.com/breach"
        },
        "mitigation_measures": incident["mitigation"]
    }
```

---

## Compliance Checklist

### HIPAA Security Rule Checklist

**Administrative Safeguards:**
- [ ] Security management process in place
- [ ] Assigned security official
- [ ] Workforce security policies and procedures
- [ ] Information access management
- [ ] Security awareness and training program
- [ ] Security incident procedures
- [ ] Contingency plan
- [ ] Periodic evaluation and response

**Physical Safeguards:**
- [ ] Facility access controls
- [ ] Workstation use policies
- [ ] Workstation security
- [ ] Device and media controls

**Technical Safeguards:**
- [ ] Access controls
- [ ] Audit controls
- [ ] Integrity controls
- [ ] Transmission security

---

## References

- [HIPAA Privacy Rule](https://www.hhs.gov/hipaa/for-professionals/privacy/laws-regulations/)
- [HIPAA Security Rule](https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/)
- [HIPAA Breach Notification Rule](https://www.hhs.gov/hipaa/for-professionals/breach-notification/)
- [NIST SP 800-66 - Security Rule Implementation](https://csrc.nist.gov/publications/detail/sp/800-66/rev-1/final)
- [HHS HIPAA Guidance](https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/)
