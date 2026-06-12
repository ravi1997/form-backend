import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock


class _Query:
    def __init__(self, docs):
        self._docs = docs

    def only(self, *fields):
        return self

    def first(self):
        return self._docs[0] if self._docs else None

    def count(self):
        return len(self._docs)

    def __iter__(self):
        return iter(list(self._docs))


def _install_package(monkeypatch, name):
    module = ModuleType(name)
    module.__path__ = []
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _install_module(monkeypatch, name, **attrs):
    module = ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def test_execute_retention_policy_updates_tenant_usage(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    responses = []
    evidence_logs = []
    settings_by_org = {}

    _install_package(monkeypatch, "services")

    class BaseService:
        def __init__(self, model, schema):
            self.model = model
            self.schema = schema

    _install_module(
        monkeypatch,
        "services.base",
        BaseService=BaseService,
    )

    _install_package(monkeypatch, "logger")
    _install_module(
        monkeypatch,
        "logger.unified_logger",
        app_logger=Mock(),
        error_logger=Mock(),
        audit_logger=Mock(),
    )

    _install_package(monkeypatch, "utils")
    class ValidationError(Exception):
        pass

    _install_module(monkeypatch, "utils.exceptions", ValidationError=ValidationError)

    class LegalHold:
        @classmethod
        def objects(cls, **kwargs):
            return _Query([])

    class EvidenceLog:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def save(self):
            evidence_logs.append(self.kwargs)
            return self

    class Form:
        @classmethod
        def objects(cls, **kwargs):
            return _Query([])

    class FormResponse:
        @classmethod
        def objects(cls, **kwargs):
            return _Query(responses)

    class TenantSettings:
        def __init__(self, organization_id):
            self.organization_id = organization_id
            self.retention_days = 30
            self.usage_submissions_count = 0
            self.save_calls = 0

        def save(self):
            self.save_calls += 1
            return self

        @classmethod
        def get_or_create(cls, organization_id):
            if organization_id not in settings_by_org:
                settings_by_org[organization_id] = cls(organization_id)
            return settings_by_org[organization_id]

    _install_package(monkeypatch, "models")
    _install_module(monkeypatch, "models.LegalHold", LegalHold=LegalHold)
    _install_module(monkeypatch, "models.EvidenceLog", EvidenceLog=EvidenceLog)
    _install_module(monkeypatch, "models.Response", FormResponse=FormResponse)
    _install_module(monkeypatch, "models.Form", Form=Form)
    _install_module(monkeypatch, "models.TenantSettings", TenantSettings=TenantSettings)

    module_path = root / "services" / "compliance_service.py"
    spec = importlib.util.spec_from_file_location("compliance_service_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)

    monkeypatch.setattr(module.ComplianceService, "is_held", lambda self, *_args: False)

    org_id = "org-retention-test"
    tenant_settings = module.TenantSettings.get_or_create(org_id)
    tenant_settings.retention_days = 30

    class Response:
        def __init__(self, response_id, submitted_at):
            self.id = response_id
            self.form = None
            self.submitted_at = submitted_at

        def delete(self):
            responses.remove(self)

    expired_response = Response(
        "resp-expired", datetime.now(timezone.utc) - timedelta(days=35)
    )
    retained_response = Response(
        "resp-active", datetime.now(timezone.utc) - timedelta(days=5)
    )
    responses.extend([expired_response, retained_response])

    result = module.ComplianceService().execute_retention_policy(org_id, "actor-1")

    assert result == {
        "pruned_count": 1,
        "held_count": 0,
        "pruned_ids": ["resp-expired"],
    }
    assert expired_response not in responses
    assert retained_response in responses
    assert tenant_settings.usage_submissions_count == 1
    assert tenant_settings.save_calls == 1
    assert evidence_logs == [
        {
            "organization_id": org_id,
            "event_type": "retention_prune",
            "actor_id": "actor-1",
            "details": {
                "response_id": "resp-expired",
                "form_id": "",
                "submitted_at": expired_response.submitted_at.isoformat(),
            },
        }
    ]
