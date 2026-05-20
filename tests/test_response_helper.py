from utils.response_helper import BaseSerializer, FormSerializer


def test_base_serializer_strips_meta_data_by_default():
    payload = {
        "id": "form-1",
        "meta_data": {"internal": True},
        "sections": [{"id": "section-1", "meta_data": {"startCollapsed": True}}],
    }

    serialized = BaseSerializer.clean_dict(payload)

    assert "meta_data" not in serialized
    assert "meta_data" not in serialized["sections"][0]


def test_form_serializer_preserves_builder_meta_data():
    payload = {
        "id": "form-1",
        "organization_id": "org-1",
        "versions": [
            {
                "version": "0.1.0",
                "sections": [
                    {
                        "id": "section-1",
                        "title": "General",
                        "meta_data": {"startCollapsed": True},
                    }
                ],
            }
        ],
    }

    serialized = FormSerializer.serialize(payload)

    assert "organization_id" not in serialized
    assert serialized["versions"][0]["sections"][0]["meta_data"] == {
        "startCollapsed": True
    }
