"""
services/compliance_registry_service.py
Compliance registry service for managing compliance standards and organizational compliance.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from mongoengine import Q

from logger.unified_logger import app_logger, error_logger, audit_logger
from services.base import BaseService
from models.compliance import (
    ComplianceStandard, OrgCompliance, ComplianceEvidence, 
    ComplianceAudit, DataProcessingRecord, ConsentRecord
)
from utils.exceptions import ValidationError, NotFoundError


class ComplianceRegistryService(BaseService):
    """Service for managing compliance standards and organizational compliance."""

    def __init__(self):
        super().__init__(model=ComplianceStandard, schema=None)

    def create_compliance_standard(self, **kwargs) -> ComplianceStandard:
        """Create a new compliance standard."""
        required_fields = ['code', 'name', 'description']
        for field in required_fields:
            if not kwargs.get(field):
                raise ValidationError(f"{field} is required")

        # Check if code already exists
        existing = ComplianceStandard.objects(code=kwargs['code']).first()
        if existing:
            raise ValidationError(f"Compliance standard with code {kwargs['code']} already exists")

        standard = ComplianceStandard(
            code=kwargs['code'],
            name=kwargs['name'],
            description=kwargs['description'],
            region=kwargs.get('region'),
            version=kwargs.get('version'),
            is_system=kwargs.get('is_system', False),
            behavioral_constraints=kwargs.get('behavioral_constraints', []),
            requirements=kwargs.get('requirements', []),
            created_by=kwargs.get('created_by'),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        standard.save()
        
        audit_logger.info(f"Compliance standard created: {standard.code} - {standard.name}")
        return standard

    def get_compliance_standards(self, include_system: bool = True) -> List[ComplianceStandard]:
        """Get all compliance standards, optionally filtering system standards."""
        query = ComplianceStandard.objects()
        if not include_system:
            query = query.filter(is_system=False)
        return list(query.order_by('name'))

    def get_compliance_standard(self, standard_id: str) -> ComplianceStandard:
        """Get a compliance standard by ID."""
        standard = ComplianceStandard.objects(id=standard_id).first()
        if not standard:
            raise NotFoundError(f"Compliance standard not found: {standard_id}")
        return standard

    def update_compliance_standard(self, standard_id: str, **kwargs) -> ComplianceStandard:
        """Update a compliance standard."""
        standard = self.get_compliance_standard(standard_id)
        
        # Cannot update system standards
        if standard.is_system:
            raise ValidationError("Cannot update system compliance standards")

        updatable_fields = ['name', 'description', 'region', 'version', 
                          'behavioral_constraints', 'requirements']
        
        for field in updatable_fields:
            if field in kwargs:
                setattr(standard, field, kwargs[field])
        
        standard.updated_at = datetime.utcnow()
        standard.save()
        
        audit_logger.info(f"Compliance standard updated: {standard.code}")
        return standard

    def delete_compliance_standard(self, standard_id: str) -> bool:
        """Delete a compliance standard."""
        standard = self.get_compliance_standard(standard_id)
        
        # Cannot delete system standards
        if standard.is_system:
            raise ValidationError("Cannot delete system compliance standards")

        # Check if any organizations are using this standard
        active_adoptions = OrgCompliance.objects(
            compliance_id=standard.id, 
            status__in=['active', 'pending']
        ).count()
        
        if active_adoptions > 0:
            raise ValidationError(f"Cannot delete standard: {active_adoptions} organizations are using it")

        standard.delete()
        audit_logger.info(f"Compliance standard deleted: {standard.code}")
        return True

    def adopt_compliance_standard(self, org_id: str, compliance_id: str, adopted_by: str, **kwargs) -> OrgCompliance:
        """Adopt a compliance standard for an organization."""
        standard = self.get_compliance_standard(compliance_id)
        
        # Check if already adopted
        existing = OrgCompliance.objects(
            org_id=org_id, 
            compliance_id=compliance_id,
            status__in=['pending', 'active']
        ).first()
        
        if existing:
            if existing.status == 'pending':
                existing.status = 'active'
                existing.adopted_at = datetime.utcnow()
                existing.adopted_by = adopted_by
                existing.effective_from = kwargs.get('effective_from', datetime.utcnow())
                existing.expires_at = kwargs.get('expires_at')
                existing.save()
                return existing
            else:
                raise ValidationError(f"Organization already has {standard.code} compliance")

        org_compliance = OrgCompliance(
            org_id=org_id,
            compliance_id=standard,
            status='active',
            adopted_at=datetime.utcnow(),
            adopted_by=adopted_by,
            effective_from=kwargs.get('effective_from', datetime.utcnow()),
            expires_at=kwargs.get('expires_at'),
            audit_frequency=kwargs.get('audit_frequency', 'annually'),
            notes=kwargs.get('notes')
        )
        org_compliance.save()
        
        audit_logger.info(f"Compliance standard adopted: {standard.code} by org {org_id}")
        return org_compliance

    def get_org_compliance(self, org_id: str) -> List[OrgCompliance]:
        """Get all compliance standards adopted by an organization."""
        return list(OrgCompliance.objects(org_id=org_id).order_by('-adopted_at'))

    def update_org_compliance(self, org_compliance_id: str, **kwargs) -> OrgCompliance:
        """Update organization compliance record."""
        org_compliance = OrgCompliance.objects(id=org_compliance_id).first()
        if not org_compliance:
            raise NotFoundError(f"Organization compliance record not found: {org_compliance_id}")

        updatable_fields = ['status', 'expires_at', 'audit_frequency', 'notes']
        for field in updatable_fields:
            if field in kwargs:
                setattr(org_compliance, field, kwargs[field])
        
        org_compliance.save()
        audit_logger.info(f"Organization compliance updated: {org_compliance.id}")
        return org_compliance

    def suspend_org_compliance(self, org_compliance_id: str, reason: str) -> OrgCompliance:
        """Suspend an organization's compliance."""
        org_compliance = self.update_org_compliance(
            org_compliance_id, 
            status='suspended',
            notes=f"Suspended: {reason}"
        )
        audit_logger.warning(f"Organization compliance suspended: {org_compliance.id}")
        return org_compliance

    def get_compliance_evidence(self, org_id: str, compliance_id: Optional[str] = None) -> List[ComplianceEvidence]:
        """Get compliance evidence for an organization."""
        query = ComplianceEvidence.objects(org_id=org_id)
        if compliance_id:
            query = query.filter(compliance_id=compliance_id)
        return list(query.order_by('-created_at'))

    def add_compliance_evidence(self, org_id: str, compliance_id: str, **kwargs) -> ComplianceEvidence:
        """Add compliance evidence."""
        required_fields = ['evidence_type', 'title', 'uploaded_by']
        for field in required_fields:
            if not kwargs.get(field):
                raise ValidationError(f"{field} is required")

        evidence = ComplianceEvidence(
            org_id=org_id,
            compliance_id=compliance_id,
            evidence_type=kwargs['evidence_type'],
            title=kwargs['title'],
            description=kwargs.get('description'),
            file_url=kwargs.get('file_url'),
            file_name=kwargs.get('file_name'),
            file_size=kwargs.get('file_size'),
            file_hash=kwargs.get('file_hash'),
            uploaded_by=kwargs['uploaded_by'],
            expiry_date=kwargs.get('expiry_date'),
            tags=kwargs.get('tags', []),
            meta_data=kwargs.get('meta_data', {}),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        evidence.save()
        
        audit_logger.info(f"Compliance evidence added: {evidence.title} for org {org_id}")
        return evidence

    def create_compliance_audit(self, org_id: str, compliance_id: str, **kwargs) -> ComplianceAudit:
        """Create a compliance audit."""
        required_fields = ['audit_type', 'title', 'created_by']
        for field in required_fields:
            if not kwargs.get(field):
                raise ValidationError(f"{field} is required")

        audit = ComplianceAudit(
            org_id=org_id,
            compliance_id=compliance_id,
            audit_type=kwargs['audit_type'],
            title=kwargs['title'],
            description=kwargs.get('description'),
            scheduled_date=kwargs.get('scheduled_date'),
            created_by=kwargs['created_by'],
            meta_data=kwargs.get('meta_data', {}),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        audit.save()
        
        audit_logger.info(f"Compliance audit created: {audit.title} for org {org_id}")
        return audit

    def get_compliance_audits(self, org_id: str, status: Optional[str] = None) -> List[ComplianceAudit]:
        """Get compliance audits for an organization."""
        query = ComplianceAudit.objects(org_id=org_id)
        if status:
            query = query.filter(status=status)
        return list(query.order_by('-created_at'))

    def create_data_processing_record(self, org_id: str, **kwargs) -> DataProcessingRecord:
        """Create a GDPR Article 30 data processing record."""
        required_fields = ['data_category', 'data_subject', 'purpose', 'legal_basis', 'created_by']
        for field in required_fields:
            if not kwargs.get(field):
                raise ValidationError(f"{field} is required")

        record = DataProcessingRecord(
            org_id=org_id,
            data_category=kwargs['data_category'],
            data_subject=kwargs['data_subject'],
            purpose=kwargs['purpose'],
            legal_basis=kwargs['legal_basis'],
            data_source=kwargs.get('data_source'),
            data_recipients=kwargs.get('data_recipients', []),
            international_transfer=kwargs.get('international_transfer', False),
            transfer_countries=kwargs.get('transfer_countries', []),
            retention_period=kwargs.get('retention_period'),
            retention_basis=kwargs.get('retention_basis'),
            security_measures=kwargs.get('security_measures', []),
            dpo_name=kwargs.get('dpo_name'),
            dpo_contact=kwargs.get('dpo_contact'),
            created_by=kwargs['created_by'],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        record.save()
        
        audit_logger.info(f"Data processing record created for org {org_id}")
        return record

    def get_data_processing_records(self, org_id: str) -> List[DataProcessingRecord]:
        """Get data processing records for an organization."""
        return list(DataProcessingRecord.objects(org_id=org_id).order_by('-created_at'))

    def create_consent_record(self, org_id: str, user_id: str, form_id: str, **kwargs) -> ConsentRecord:
        """Create a GDPR consent record."""
        required_fields = ['consent_type', 'consent_text']
        for field in required_fields:
            if not kwargs.get(field):
                raise ValidationError(f"{field} is required")

        # Check for existing active consent
        existing = ConsentRecord.objects(
            org_id=org_id,
            user_id=user_id,
            form_id=form_id,
            consent_type=kwargs['consent_type'],
            status='active'
        ).first()
        
        if existing:
            # Withdraw existing consent
            existing.status = 'withdrawn'
            existing.withdrawal_date = datetime.utcnow()
            existing.withdrawal_reason = 'New consent given'
            existing.save()

        consent = ConsentRecord(
            org_id=org_id,
            user_id=user_id,
            form_id=form_id,
            consent_type=kwargs['consent_type'],
            consent_version=kwargs.get('consent_version', '1.0'),
            status='active',
            consent_text=kwargs['consent_text'],
            consent_date=datetime.utcnow(),
            consent_ip=kwargs.get('consent_ip'),
            consent_user_agent=kwargs.get('consent_user_agent'),
            expires_at=kwargs.get('expires_at'),
            auto_renew=kwargs.get('auto_renew', False),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        consent.save()
        
        audit_logger.info(f"Consent record created: {consent.consent_type} for user {user_id}")
        return consent

    def get_user_consents(self, org_id: str, user_id: str) -> List[ConsentRecord]:
        """Get consent records for a user."""
        return list(ConsentRecord.objects(
            org_id=org_id,
            user_id=user_id
        ).order_by('-created_at'))

    def withdraw_consent(self, consent_id: str, reason: str) -> ConsentRecord:
        """Withdraw a consent."""
        consent = ConsentRecord.objects(id=consent_id).first()
        if not consent:
            raise NotFoundError(f"Consent record not found: {consent_id}")

        if consent.status != 'active':
            raise ValidationError("Consent is not active and cannot be withdrawn")

        consent.status = 'withdrawn'
        consent.withdrawal_date = datetime.utcnow()
        consent.withdrawal_reason = reason
        consent.save()
        
        audit_logger.info(f"Consent withdrawn: {consent.id}")
        return consent

    def get_compliance_summary(self, org_id: str) -> Dict[str, Any]:
        """Get a summary of compliance status for an organization."""
        org_compliances = self.get_org_compliance(org_id)
        audits = self.get_compliance_audits(org_id)
        evidence = self.get_compliance_evidence(org_id)
        
        active_standards = [oc for oc in org_compliances if oc.status == 'active']
        pending_audits = [a for a in audits if a.status in ['scheduled', 'in_progress']]
        overdue_audits = [a for a in pending_audits if a.scheduled_date and a.scheduled_date < datetime.utcnow()]
        
        return {
            'total_standards': len(org_compliances),
            'active_standards': len(active_standards),
            'pending_audits': len(pending_audits),
            'overdue_audits': len(overdue_audits),
            'total_evidence': len(evidence),
            'verified_evidence': len([e for e in evidence if e.is_verified]),
            'compliance_standards': [
                {
                    'id': str(oc.compliance_id.id),
                    'code': oc.compliance_id.code,
                    'name': oc.compliance_id.name,
                    'status': oc.status,
                    'adopted_at': oc.adopted_at.isoformat() if oc.adopted_at else None,
                    'expires_at': oc.expires_at.isoformat() if oc.expires_at else None
                }
                for oc in org_compliances
            ]
        }

    def seed_default_compliance_standards(self):
        """Seed default compliance standards (GDPR, HIPAA, ISO 27001)."""
        default_standards = [
            {
                'code': 'GDPR',
                'name': 'General Data Protection Regulation',
                'description': 'EU regulation on data protection and privacy for individuals within the European Union',
                'region': 'EU',
                'version': '2018',
                'is_system': True,
                'behavioral_constraints': [
                    {
                        'type': 'consent_checkbox',
                        'name': 'Data Processing Consent',
                        'description': 'Require explicit consent for data processing',
                        'config': {'required': True, 'default_text': 'I consent to the processing of my personal data'},
                        'is_mandatory': True,
                        'enforcement_level': 'required'
                    },
                    {
                        'type': 'audit_logging',
                        'name': 'Comprehensive Audit Logging',
                        'description': 'Log all data access and processing activities',
                        'config': {'log_level': 'detailed', 'retention_days': 365},
                        'is_mandatory': True,
                        'enforcement_level': 'required'
                    },
                    {
                        'type': 'data_retention',
                        'name': 'Data Retention Policy',
                        'description': 'Implement data retention policies',
                        'config': {'default_retention_days': 365, 'max_retention_days': 1825},
                        'is_mandatory': True,
                        'enforcement_level': 'required'
                    }
                ]
            },
            {
                'code': 'HIPAA',
                'name': 'Health Insurance Portability and Accountability Act',
                'description': 'US law providing data privacy and security provisions for safeguarding medical information',
                'region': 'US',
                'version': '1996',
                'is_system': True,
                'behavioral_constraints': [
                    {
                        'type': 'audit_logging',
                        'name': 'HIPAA Audit Logging',
                        'description': 'Log all access to protected health information',
                        'config': {'log_level': 'hipaa', 'retention_days': 2555},  # 7 years
                        'is_mandatory': True,
                        'enforcement_level': 'required'
                    },
                    {
                        'type': 'security_policy',
                        'name': 'HIPAA Security Policy',
                        'description': 'Implement HIPAA security measures',
                        'config': {'encryption_required': True, 'access_controls': True},
                        'is_mandatory': True,
                        'enforcement_level': 'required'
                    }
                ]
            },
            {
                'code': 'ISO27001',
                'name': 'ISO/IEC 27001 Information Security Management',
                'description': 'International standard for information security management systems',
                'region': 'Global',
                'version': '2013',
                'is_system': True,
                'behavioral_constraints': [
                    {
                        'type': 'security_policy',
                        'name': 'ISMS Security Policy',
                        'description': 'Implement comprehensive information security management',
                        'config': {'policy_level': 'iso27001', 'risk_assessment': True},
                        'is_mandatory': True,
                        'enforcement_level': 'required'
                    },
                    {
                        'type': 'audit_logging',
                        'name': 'Security Incident Logging',
                        'description': 'Log all security incidents',
                        'config': {'log_level': 'security', 'retention_days': 2555},
                        'is_mandatory': True,
                        'enforcement_level': 'required'
                    }
                ]
            }
        ]

        for standard_data in default_standards:
            existing = ComplianceStandard.objects(code=standard_data['code']).first()
            if not existing:
                self.create_compliance_standard(**standard_data)
                app_logger.info(f"Created default compliance standard: {standard_data['code']}")


compliance_registry_service = ComplianceRegistryService()