import models

from services.nlp_service import NLPSearchService


class _FakeRecord:
    saved_records = []

    def __init__(
        self,
        user_id,
        form_id,
        query,
        results_count=0,
        parsed_intent=None,
        search_type="nlp",
        cached=False,
    ):
        self.id = f"search-{len(self.saved_records) + 1}"
        self.user_id = user_id
        self.form_id = form_id
        self.query = query
        self.results_count = results_count
        self.parsed_intent = parsed_intent or {}
        self.search_type = search_type
        self.cached = cached
        self.created_at = None

    def save(self):
        self.saved_records.append(self)
        return self

    @classmethod
    def objects(cls, **filters):
        records = [
            record
            for record in cls.saved_records
            if all(getattr(record, key) == value for key, value in filters.items())
        ]
        return _FakeQuery(records)


class _FakeQuery(list):
    def order_by(self, *_args, **_kwargs):
        return self

    def skip(self, count):
        return _FakeQuery(self[count:])

    def limit(self, count):
        return _FakeQuery(self[:count])

    def delete(self):
        deleted = len(self)
        for record in list(self):
            _FakeRecord.saved_records.remove(record)
        return deleted


def test_nlp_search_service_persists_and_reads_history(monkeypatch):
    _FakeRecord.saved_records = []
    monkeypatch.setattr(models, "SearchHistory", _FakeRecord, raising=False)

    search_id = NLPSearchService.save_search(
        user_id="user-1",
        form_id="form-1",
        query="blood pressure",
        results_count=3,
        parsed_intent={"intent": "search"},
        search_type="semantic",
        cached=True,
    )

    assert search_id == "search-1"

    history = NLPSearchService.get_user_search_history(
        user_id="user-1", form_id="form-1", limit=10, offset=0
    )
    assert history[0]["query"] == "blood pressure"
    assert history[0]["results_count"] == 3

    popular = NLPSearchService.get_popular_queries(form_id="form-1", limit=10)
    assert popular[0]["query"] == "blood pressure"

    deleted = NLPSearchService.clear_user_search_history(
        user_id="user-1", form_id="form-1"
    )
    assert deleted == 1
    assert NLPSearchService.get_user_search_history(
        user_id="user-1", form_id="form-1", limit=10, offset=0
    ) == []
