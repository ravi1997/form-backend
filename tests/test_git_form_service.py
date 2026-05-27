import pytest
import uuid
from services.git_form_service import GitFormService
from models.FormCommit import FormCommit


def test_git_form_service_diff_and_patch():
    # Base structure
    src = {
        "title": "Old Form Title",
        "ui_type": "flex",
        "sections": [
            {
                "id": "sec-1",
                "label": "First Section",
                "questions": [{"id": "q-1", "type": "short_text", "label": "Username"}],
            }
        ],
    }

    # Target structure with updates
    dst = {
        "title": "New Form Title",
        "ui_type": "flex",
        "sections": [
            {
                "id": "sec-1",
                "label": "Modified Section Label",
                "questions": [
                    {"id": "q-1", "type": "short_text", "label": "Username"},
                    {"id": "q-2", "type": "number", "label": "Age"},
                ],
            }
        ],
    }

    # 1. Calculate diff (JSON Patches)
    ops = GitFormService.diff(src, dst)
    assert len(ops) > 0

    # 2. Apply patch to source
    patched = GitFormService.patch(src, ops)

    # 3. Confirm target is reached
    assert patched == dst


def test_git_form_service_3way_merge_auto():
    # Base structure
    base = {
        "title": "Patient Form",
        "description": "General Patient Intake Form",
        "style": {"color": "#4A90E2"},
    }

    # Mine (edited description and color)
    mine = {
        "title": "Patient Form",
        "description": "Patient Intake Form V2",
        "style": {"color": "#673AB7"},
    }

    # Theirs (edited title, untouched description/color)
    theirs = {
        "title": "Patient OPD Intake Form",
        "description": "General Patient Intake Form",
        "style": {"color": "#4A90E2"},
    }

    # Run merge (changes are on separate keys, should auto-merge with no conflicts)
    merged, conflicts = GitFormService.calculate_3way_merge(base, mine, theirs)

    assert len(conflicts) == 0
    assert merged["title"] == "Patient OPD Intake Form"
    assert merged["description"] == "Patient Intake Form V2"
    assert merged["style"]["color"] == "#673AB7"


def test_git_form_service_3way_merge_conflict():
    # Base structure
    base = {"title": "Initial Title", "status": "draft"}

    # Mine
    mine = {"title": "My Workspace Title", "status": "draft"}

    # Theirs
    theirs = {"title": "Server Main Title", "status": "draft"}

    # Run merge: changes to same key "title" should trigger conflict
    merged, conflicts = GitFormService.calculate_3way_merge(base, mine, theirs)

    assert len(conflicts) == 1
    assert conflicts[0]["path"] == "/title"
    assert conflicts[0]["mine"] == "My Workspace Title"
    assert conflicts[0]["theirs"] == "Server Main Title"
