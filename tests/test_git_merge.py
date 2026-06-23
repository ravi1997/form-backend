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
