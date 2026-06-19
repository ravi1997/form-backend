"""
models/compliance.py
Compliance registry and behavioral enforcement models.
"""

from mongoengine import (
    StringField, ListField, EmbeddedDocumentField, ReferenceField, DictField,
    BooleanField, DateTimeField, IntField, EmbeddedDocument
)
from models.base import BaseDocument, SoftDeleteMixin, BaseEmbeddedDocument


class ComplianceStandard(BaseDocument):
    """Compliance standard definition (GDPR, HIPAA, ISO 27001, etc.)."""

    meta = {
        "collection": "compliance_standards",
        "indexes": [
            {"fields": ["code"], "unique": True},
            {"fields": ["name"]},
            {"fields": ["region"]},
            {"fields": ["is_system"]},
        ],
        "index_background": True,
    }

    code = StringField(required=True, unique=True)  # GDPR, HIPAA, ISO27001
    name = StringField(required=True)
    description = StringField()
    region = StringField()  # EU, US, Global, etc.
    version = StringField()
    is_system = BooleanField(default=True)  # System standards cannot be deleted
    behavioral_constraints = ListField(DictField())  # Behavioral constraint definitions
    requirements = ListField(DictField())  # Detailed requirements
    created_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField()
    updated_at = DateTimeField()


class ComplianceConstraint(BaseEmbeddedDocument):
    """Individual behavioral constraint for a compliance standard."""

    type = StringField(required=True)  # consent_checkbox, audit_logging, security_policy, etc.
    name = StringField(required=True)
    description = StringField()
    config = DictField()  # Configuration for the constraint
    is_mandatory = BooleanField(default=True)
    enforcement_level = StringField(choices=["required", "recommended", "optional"], default="required")


class OrgCompliance(BaseDocument, SoftDeleteMixin):
    """Organization's adoption of a compliance standard."""

    meta = {
        "collection": "org_compliance",
        "indexes": [
            {"fields": ["org_id", "compliance_id"], "unique": True},
            {"fields": ["org_id", "status"]},
            {"fields": ["compliance_id", "status"]},
            {"fields": ["effective_from"]},
            {"fields": ["expires_at"]},
        ],
        "index_background": True,
    }

    org_id = StringField(required=True, trim=True)
    compliance_id = ReferenceField("ComplianceStandard", required=True, reverse_delete_rule=3)
    status = StringField(choices=["pending", "active", "suspended", "expired"], default="pending")
    adopted_at = DateTimeField()
    adopted_by = ReferenceField("User", reverse_delete_rule=3)
    effective_from = DateTimeField()
    expires_at = DateTimeField()
    audit_frequency = StringField(choices=["monthly", "quarterly", "annually"], default="annually")
    last_audit_date = DateTimeField()
    next_audit_date = DateTimeField()
    auditor_name = StringField()
    certification_url = StringField()
    notes = StringField()
    meta_data = DictField()


class ComplianceEvidence(BaseDocument):
    """Evidence of compliance activities."""

    meta = {
        "collection": "compliance_evidence",
        "indexes": [
            {"fields": ["org_id", "compliance_id"]},
            {"fields": ["org_id", "evidence_type"]},
            {"fields": ["compliance_id", "evidence_type"]},
            {"fields": ["created_at"]},
        ],
        "index_background": True,
    }

    org_id = StringField(required=True, trim=True)
    compliance_id = ReferenceField("ComplianceStandard", required=True, reverse_delete_rule=3)
    evidence_type = StringField(required=True)  # audit_log, policy_document, training_record, etc.
    title = StringField(required=True)
    description = StringField()
    file_url = StringField()  # URL to evidence file
    file_name = StringField()
    file_size = IntField()
    file_hash = StringField()
    uploaded_by = ReferenceField("User", reverse_delete_rule=3)
    verified_by = ReferenceField("User", reverse_delete_rule=3)
    verified_at = DateTimeField()
    is_verified = BooleanField(default=False)
    expiry_date = DateTimeField()
    tags = ListField(StringField())
    meta_data = DictField()
    created_at = DateTimeField()
    updated_at = DateTimeField()


class ComplianceAudit(BaseDocument):
    """Compliance audit records."""

    meta = {
        "collection": "compliance_audits",
        "indexes": [
            {"fields": ["org_id", "compliance_id"]},
            {"fields": ["org_id", "audit_type"]},
            {"fields": ["status"]},
            {"fields": ["scheduled_date"]},
            {"fields": ["completed_date"]},
        ],
        "index_background": True,
    }

    org_id = StringField(required=True, trim=True)
    compliance_id = ReferenceField("ComplianceStandard", required=True, reverse_delete_rule=3)
    audit_type = StringField(choices=["internal", "external", "automated"])
    title = StringField(required=True)
    description = StringField()
    status = StringField(choices=["scheduled", "in_progress", "completed", "failed"], default="scheduled")
    scheduled_date = DateTimeField()
    started_date = DateTimeField()
    completed_date = DateTimeField()
    auditor_name = StringField()
    auditor_contact = StringField()
    findings = ListField(DictField())
    recommendations = ListField(StringField())
    remediation_deadline = DateTimeField()
    report_url = StringField()
    created_by = ReferenceField("User", reverse_delete_rule=3)
    meta_data = DictField()
    created_at = DateTimeField()
    updated_at = DateTimeField()


class DataProcessingRecord(BaseDocument):
    """GDPR Article 30 Record of Processing Activities."""

    meta = {
        "collection": "data_processing_records",
        "indexes": [
            {"fields": ["org_id", "data_category"]},
            {"fields": ["org_id", "purpose"]},
            {"fields": ["org_id", "data_subject"]},
            {"fields": ["retention_period"]},
        ],
        "index_background": True,
    }

    org_id = StringField(required=True, trim=True)
    data_category = StringField(required=True)  # personal, sensitive, health, etc.
    data_subject = StringField(required=True)  # customers, employees, etc.
    purpose = StringField(required=True)  # form_responses, analytics, etc.
    legal_basis = StringField(required=True)  # consent, legitimate_interest, etc.
    data_source = StringField()  # form_submissions, manual_entry, etc.
    data_recipients = ListField(StringField())  # third_parties, internal_departments
    international_transfer = BooleanField(default=False)
    transfer_countries = ListField(StringField())
    retention_period = StringField()  # 6_months, 1_year, etc.
    retention_basis = StringField()  # legal_requirement, business_need, etc.
    security_measures = ListField(StringField())
    dpo_name = StringField()  # Data Protection Officer
    dpo_contact = StringField()
    created_by = ReferenceField("User", reverse_delete_rule=3)
    created_at = DateTimeField()
    updated_at = DateTimeField()


class ConsentRecord(BaseDocument):
    """GDPR consent records."""

    meta = {
        "collection": "consent_records",
        "indexes": [
            {"fields": ["org_id", "user_id"]},
            {"fields": ["org_id", "form_id"]},
            {"fields": ["user_id", "form_id"]},
            {"fields": ["consent_type"]},
            {"fields": ["status"]},
            {"fields": ["expires_at"]},
        ],
        "index_background": True,
    }

    org_id = StringField(required=True, trim=True)
    user_id = ReferenceField("User", required=True, reverse_delete_rule=3)
    form_id = ReferenceField("Form", reverse_delete_rule=3)
    consent_type = StringField(required=True)  # data_processing, marketing, analytics, etc.
    consent_version = StringField()
    status = StringField(choices=["active", "withdrawn", "expired"], default="active")
    consent_text = StringField()
    consent_date = DateTimeField()
    consent_ip = StringField()
    consent_user_agent = StringField()
    withdrawal_date = DateTimeField()
    withdrawal_reason = StringField()
    expires_at = DateTimeField()
    auto_renew = BooleanField(default=False)
    created_at = DateTimeField()
    updated_at = DateTimeField()