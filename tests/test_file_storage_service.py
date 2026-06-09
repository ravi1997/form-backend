import base64
from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from services.file_storage_service import FileStorageService
from utils.exceptions import ValidationError


class _TenantSettingsStub:
    def __init__(self, storage_limit_mb=1, usage_storage_bytes=0):
        self.storage_limit_mb = storage_limit_mb
        self.usage_storage_bytes = usage_storage_bytes

    def save(self):
        return self


def _make_file(name="example.txt", content=b"hello world"):
    return FileStorage(stream=BytesIO(content), filename=name, content_type="text/plain")


def test_save_file_blocks_when_tenant_storage_quota_is_exceeded(tmp_path, monkeypatch):
    service = FileStorageService(upload_folder=str(tmp_path))
    file_obj = _make_file(content=b"x" * 16)

    monkeypatch.setattr(
        "services.file_storage_service.generate_secure_filename",
        lambda value: value.replace("-", "_"),
    )

    tenant_root = tmp_path / "org_1" / "form_1" / "question_1"
    tenant_root.mkdir(parents=True)
    (tenant_root / "existing.bin").write_bytes(b"y" * (1024 * 1024 + 1))

    monkeypatch.setattr(
        "services.file_storage_service.TenantSettings.get_or_create",
        lambda _organization_id: _TenantSettingsStub(storage_limit_mb=1),
    )

    with pytest.raises(ValidationError):
        service.save_file(
            file=file_obj,
            organization_id="org-1",
            form_id="form-1",
            question_id="question-1",
        )


def test_save_file_updates_tenant_usage_after_write(tmp_path, monkeypatch):
    tenant_settings = _TenantSettingsStub(storage_limit_mb=1, usage_storage_bytes=0)
    service = FileStorageService(upload_folder=str(tmp_path))
    file_obj = _make_file(content=b"x" * 16)

    monkeypatch.setattr(
        "services.file_storage_service.generate_secure_filename",
        lambda value: value.replace("-", "_"),
    )

    monkeypatch.setattr(
        "services.file_storage_service.TenantSettings.get_or_create",
        lambda _organization_id: tenant_settings,
    )

    signed_url = service.save_file(
        file=file_obj,
        organization_id="org-1",
        form_id="form-1",
        question_id="question-1",
    )

    assert signed_url.startswith("/mahasangraha/api/v1/files/download?token=")
    assert tenant_settings.usage_storage_bytes > 0


def test_save_base64_signature_updates_tenant_usage(tmp_path, monkeypatch):
    tenant_settings = _TenantSettingsStub(storage_limit_mb=1, usage_storage_bytes=0)
    service = FileStorageService(upload_folder=str(tmp_path))
    refresh_calls = []

    monkeypatch.setattr(
        "services.file_storage_service.TenantSettings.get_or_create",
        lambda _organization_id: tenant_settings,
    )
    monkeypatch.setattr(
        service,
        "_refresh_storage_usage",
        lambda organization_id: refresh_calls.append(organization_id),
    )

    signature_data = "data:image/png;base64," + base64.b64encode(b"signature-bytes").decode()
    signed_url = service.save_base64_signature(
        signature_data=signature_data,
        organization_id="org-1",
        form_id="form-1",
    )

    assert signed_url.startswith("/mahasangraha/api/v1/files/download?token=")
    assert refresh_calls == ["org-1"]
