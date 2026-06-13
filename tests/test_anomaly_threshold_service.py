from types import SimpleNamespace

import services.anomaly_detection_service as anomaly_module
from services.anomaly_detection_service import AnomalyDetectionService


class _FakeQuery(list):
    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, count):
        return _FakeQuery(self[:count])

    def first(self):
        return self[0] if self else None


class _FakeThreshold:
    saved = []

    def __init__(
        self,
        form_id,
        organization_id,
        thresholds,
        baseline_stats,
        sensitivity,
        response_count,
        created_by,
        reason,
        is_manual,
    ):
        self.id = f"threshold-{len(self.saved) + 1}"
        self.form_id = form_id
        self.organization_id = organization_id
        self.thresholds = thresholds
        self.baseline_stats = baseline_stats
        self.sensitivity = sensitivity
        self.response_count = response_count
        self.created_by = created_by
        self.reason = reason
        self.is_manual = is_manual
        self.created_at = SimpleNamespace(isoformat=lambda: "2026-06-13T00:00:00Z")

    def save(self):
        self.saved.append(self)
        return self

    @classmethod
    def objects(cls, **filters):
        records = [record for record in cls.saved if all(getattr(record, k) == v for k, v in filters.items())]
        return _FakeQuery(records)


def test_anomaly_threshold_service_persists_history(monkeypatch):
    _FakeThreshold.saved = []
    monkeypatch.setattr(anomaly_module, "AnomalyThreshold", _FakeThreshold, raising=False)
    monkeypatch.setattr(
        anomaly_module,
        "Form",
        SimpleNamespace(
            objects=lambda **_kwargs: SimpleNamespace(
                first=lambda: SimpleNamespace(organization_id="org-1")
            )
        ),
        raising=False,
    )

    service = AnomalyDetectionService()
    result = service.set_manual_threshold(
        form_id="form-1",
        thresholds={"z_score_threshold": 2.5},
        created_by="user-1",
        reason="too many false positives",
    )

    assert result["threshold_id"] == "threshold-1"
    history = service.get_threshold_history(form_id="form-1", limit=10)
    assert history[0]["thresholds"] == {"z_score_threshold": 2.5}
    latest = service.get_latest_threshold(form_id="form-1")
    assert latest["threshold_id"] == "threshold-1"
