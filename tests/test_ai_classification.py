import pytest
from unittest.mock import patch, MagicMock
from models import Form, FormResponse, TaxonomyItem, FormVersion
from tasks.ai_tasks import async_classify_response_tags
from services.ai_service import ai_service
import mongoengine
import mongomock


@pytest.fixture(scope="function")
def mock_db_conn():
    """Establish an isolated, in-memory mock database connection using mongomock."""
    try:
        mongoengine.disconnect()
    except Exception:
        pass

    # Official way to connect MongoEngine to mongomock
    mongoengine.connect(
        "test_classification_db", mongo_client_class=mongomock.MongoClient
    )

    yield

    try:
        mongoengine.disconnect()
    except Exception:
        pass


def test_async_classify_response_tags_success(app, mock_db_conn):
    """
    Tests that response text content is successfully evaluated against a form's AI taxonomy
    and correctly classified tags are updated on both the response model and its metadata.
    """
    org_id = "test-org"

    # Create taxonomy items
    item_bug = TaxonomyItem(
        category_name="Bug Report",
        description="Issues relating to system crashes, errors, or unexpected behavior.",
        keywords=["crash", "error", "fail", "broken", "bug"],
    )
    item_feature = TaxonomyItem(
        category_name="Feature Request",
        description="Suggestions or requests for new features, tools, or enhancements.",
        keywords=["request", "suggest", "improve", "want", "add"],
    )

    # Save a real form in our in-memory mongomock database
    form = Form(
        title="User Feedback Form",
        slug="user-feedback-form",
        organization_id=org_id,
        created_by="user-123",
        classification_enabled=True,
        classification_taxonomy=[item_bug, item_feature],
    )
    form.save()

    # Create a real response document
    response = FormResponse(
        form=form,
        organization_id=org_id,
        submitted_by="user-abc",
        data={
            "feedback_text": "I encountered an error and the application keeps crashing when trying to save a form. Please fix this bug.",
            "username": "tester",
        },
        tags=[],
    )

    # Save the response. We patch the decrypt/dereference save check since we don't have FormVersions snapshots in test
    with patch("models.Response.FormResponse.save", autospec=True) as mock_save:

        def side_effect(self, *args, **kwargs):
            # Bypass dereference decryption checks and save standard fields directly via MongoEngine
            return mongoengine.Document.save(self, *args, **kwargs)

        mock_save.side_effect = side_effect
        response.save()

    # 2. Invoke Celery classification task
    result = async_classify_response_tags(str(response.id), org_id)

    # 3. Assert correct taxonomy classification outputs
    assert result["status"] == "success"
    assert "Bug Report" in result["tags_applied"]
    assert "Feature Request" not in result["tags_applied"]

    # Retrieve updated response doc to verify DB write
    updated_response = FormResponse.objects(id=response.id).first()
    assert "Bug Report" in updated_response.tags
    assert "Bug Report" in updated_response.ai_results["classification"]["tags"]
    assert updated_response.ai_results["classification"]["provider"] == "heuristic"
