import pytest
from services.git_form_service import GitFormService

def test_3way_merge_no_conflicts():
    base = {"title": "Form V1", "fields": {"name": "Text", "age": "Number"}}
    mine = {"title": "Form V1 - Mine", "fields": {"name": "Text", "age": "Number"}}
    theirs = {"title": "Form V1", "fields": {"name": "Text", "age": "Number", "email": "Email"}}

    merged, conflicts = GitFormService.calculate_3way_merge(base, mine, theirs)
    
    assert len(conflicts) == 0
    assert merged["title"] == "Form V1 - Mine"
    assert "email" in merged["fields"]

def test_3way_merge_with_conflicts_unresolved():
    base = {"title": "Form V1", "fields": {"name": "Text"}}
    mine = {"title": "Form V1 - Mine", "fields": {"name": "Text"}}
    theirs = {"title": "Form V1 - Theirs", "fields": {"name": "Text"}}

    merged, conflicts = GitFormService.calculate_3way_merge(base, mine, theirs)
    
    assert len(conflicts) == 1
    assert conflicts[0]["path"] == "/title"
    assert conflicts[0]["mine"] == "Form V1 - Mine"
    assert conflicts[0]["theirs"] == "Form V1 - Theirs"
    assert conflicts[0]["base"] == "Form V1"

def test_3way_merge_resolved_mine():
    base = {"title": "Form V1", "fields": {"name": "Text"}}
    mine = {"title": "Form V1 - Mine", "fields": {"name": "Text"}}
    theirs = {"title": "Form V1 - Theirs", "fields": {"name": "Text"}}

    resolutions = {"/title": "mine"}
    merged, conflicts = GitFormService.calculate_3way_merge(base, mine, theirs, resolutions)
    
    assert len(conflicts) == 0
    assert merged["title"] == "Form V1 - Mine"

def test_3way_merge_resolved_theirs():
    base = {"title": "Form V1", "fields": {"name": "Text"}}
    mine = {"title": "Form V1 - Mine", "fields": {"name": "Text"}}
    theirs = {"title": "Form V1 - Theirs", "fields": {"name": "Text"}}

    resolutions = {"/title": "theirs"}
    merged, conflicts = GitFormService.calculate_3way_merge(base, mine, theirs, resolutions)
    
    assert len(conflicts) == 0
    assert merged["title"] == "Form V1 - Theirs"


from unittest.mock import MagicMock
from engines.form_engine import FormEngine
from models.form import Form
from utils.exceptions import StateTransitionError

def test_list_branches():
    engine = FormEngine()
    form = MagicMock()
    form.branches = {"main": "commit_1", "dev": "commit_2"}
    
    with MagicMock() as mock_objects:
        mock_objects.first.return_value = form
        Form.objects = MagicMock(return_value=mock_objects)
        
        branches = engine.list_branches("form_1", "org_1")
        assert "main" in branches
        assert "dev" in branches

def test_delete_branch_main():
    engine = FormEngine()
    with pytest.raises(StateTransitionError):
        engine.delete_branch("form_1", "org_1", "main")

def test_delete_branch_success():
    engine = FormEngine()
    form = MagicMock()
    form.branches = {"main": "commit_1", "dev": "commit_2"}
    
    with MagicMock() as mock_objects:
        mock_objects.first.return_value = form
        Form.objects = MagicMock(return_value=mock_objects)
        
        result = engine.delete_branch("form_1", "org_1", "dev")
        assert result["deleted_branch"] == "dev"
        assert "dev" not in form.branches

