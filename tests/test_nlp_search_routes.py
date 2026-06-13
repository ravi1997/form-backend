from types import SimpleNamespace

from routes.v1.form.nlp_search import get_popular_queries, save_search_history


def _unwrap(view):
    while hasattr(view, "__wrapped__"):
        view = view.__wrapped__
    return view


def test_nlp_search_history_routes_use_persisted_service(app, monkeypatch):
    saved = []

    monkeypatch.setattr(
        "routes.v1.form.nlp_search.get_current_user",
        lambda: SimpleNamespace(id="user-1", organization_id="org-1"),
    )
    monkeypatch.setattr(
        "routes.v1.form.nlp_search.NLPSearchService.save_search",
        lambda **kwargs: saved.append(kwargs) or "search-1",
    )
    monkeypatch.setattr(
        "routes.v1.form.nlp_search.NLPSearchService.get_popular_queries_cached",
        lambda **kwargs: [{"query": "blood pressure", "count": 2}],
    )

    with app.test_request_context(
        "/forms/form-1/search-history",
        json={
            "query": "blood pressure",
            "results_count": 2,
            "parsed_intent": {"intent": "search"},
            "search_type": "nlp",
            "cached": False,
        },
    ):
        response, status_code = _unwrap(save_search_history)("form-1")
        payload = response.get_json()

    assert status_code == 201
    assert payload["id"] == "search-1"
    assert saved[0]["form_id"] == "form-1"
    assert saved[0]["query"] == "blood pressure"

    with app.test_request_context("/forms/form-1/popular-queries?limit=10"):
        response = _unwrap(get_popular_queries)("form-1")
        payload = response.get_json()

    assert payload["cached"] is True
    assert payload["popular_queries"][0]["query"] == "blood pressure"
