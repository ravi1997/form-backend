import json
import uuid
from pathlib import Path

import requests

BASE = "http://localhost:8051"
REPORT = Path("postman_route_live_status.md")


def add(rows, group, name, method, url, status, note):
    rows.append((group, name, method, url, status, note))


def main():
    s = requests.Session()
    rows = []
    org_id = f"org_{uuid.uuid4().hex[:8]}"
    email = f"codex.{uuid.uuid4().hex[:6]}@example.com"
    username = f"codex_{uuid.uuid4().hex[:8]}"
    mobile = str(9000000000 + int(uuid.uuid4().hex[:8], 16) % 1000000000)
    password = os.environ.get("DEV_ALICE_PASSWORD")
    if not password:
        print("DEV_ALICE_PASSWORD environment variable must be set explicitly.")
        raise SystemExit(1)

    # Health
    r = s.get(f"{BASE}/form/health", allow_redirects=False)
    add(
        rows,
        "0. Health Check",
        "Health Check",
        "GET",
        "/form/health",
        r.status_code,
        "Redirects with 308; add trailing slash or normalize route.",
    )
    r = s.get(f"{BASE}/form/api/v1/ai/health")
    add(
        rows,
        "0. Health Check",
        "AI Health Check",
        "GET",
        "/form/api/v1/ai/health",
        r.status_code,
        "OK" if r.status_code == 200 else r.text[:120],
    )

    # Auth
    reg = s.post(
        f"{BASE}/form/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "username": username,
            "user_type": "employee",
            "mobile": mobile,
            "roles": ["admin"],
            "organization_id": org_id,
        },
    )
    add(
        rows,
        "1. Authentication",
        "1.1 Register",
        "POST",
        "/form/api/v1/auth/register",
        reg.status_code,
        "Created test user" if reg.status_code == 201 else reg.text[:120],
    )
    login = s.post(
        f"{BASE}/form/api/v1/auth/login", json={"email": email, "password": password}
    )
    add(
        rows,
        "1. Authentication",
        "1.2 Login (password)",
        "POST",
        "/form/api/v1/auth/login",
        login.status_code,
        "Access token issued" if login.status_code == 200 else login.text[:120],
    )
    token = login.json().get("data", {}).get("access_token") if login.ok else None
    if token:
        s.headers["Authorization"] = f"Bearer {token}"

    # User
    profile = s.get(f"{BASE}/form/api/v1/user/profile")
    add(
        rows,
        "2. User Management",
        "2.1 Get My Profile",
        "GET",
        "/form/api/v1/user/profile",
        profile.status_code,
        "OK" if profile.status_code == 200 else profile.text[:120],
    )
    pwd = s.post(
        f"{BASE}/form/api/v1/user/change-password",
        json={"current_password": password, "new_password": "BetterP@ssWord2026"},
    )
    add(
        rows,
        "2. User Management",
        "2.2 Change Password",
        "POST",
        "/form/api/v1/user/change-password",
        pwd.status_code,
        "OK" if pwd.status_code == 200 else pwd.text[:120],
    )

    # Project
    proj = s.post(
        f"{BASE}/form/api/v1/projects/",
        json={
            "title": "Patient Intake",
            "description": "Project for testing",
            "help_text": "Route status validation run",
            "organization_id": org_id,
            "status": "draft",
            "sub_projects": [],
            "forms": [],
            "tags": ["intake"],
            "triggers": [],
        },
    )
    add(
        rows,
        "2b. Project Management",
        "2b.1 Create Project",
        "POST",
        "/form/api/v1/projects/",
        proj.status_code,
        "OK" if proj.status_code == 201 else proj.text[:120],
    )
    project_id = proj.json().get("data", {}).get("id") if proj.ok else None
    if project_id:
        got = s.get(f"{BASE}/form/api/v1/projects/{project_id}")
        add(
            rows,
            "2b. Project Management",
            "2b.3 Get Project",
            "GET",
            f"/form/api/v1/projects/{project_id}",
            got.status_code,
            "OK" if got.status_code == 200 else got.text[:120],
        )
        upd = s.put(
            f"{BASE}/form/api/v1/projects/{project_id}",
            json={
                "title": "Patient Intake Updated",
                "description": "upd",
                "status": "draft",
                "tags": ["intake"],
            },
        )
        add(
            rows,
            "2b. Project Management",
            "2b.4 Update Project",
            "PUT",
            f"/form/api/v1/projects/{project_id}",
            upd.status_code,
            (
                "Validation failed with example payload"
                if upd.status_code == 400
                else "OK"
            ),
        )
        form = s.post(
            f"{BASE}/form/api/v1/projects/{project_id}/forms",
            json={
                "title": "Patient Intake Form",
                "slug": f"patient-intake-{uuid.uuid4().hex[:6]}",
                "description": "Collect patient information",
                "status": "draft",
                "ui_type": "flex",
                "supported_languages": ["en"],
                "default_language": "en",
                "tags": ["intake"],
                "is_public": False,
                "is_template": False,
                "sections": [],
                "created_by": "system",
            },
        )
        add(
            rows,
            "2b. Project Management",
            "2b.6 Create Form in Project",
            "POST",
            f"/form/api/v1/projects/{project_id}/forms",
            form.status_code,
            (
                "created_by required in schema; OK"
                if form.status_code in (200, 201)
                else form.text[:160]
            ),
        )

    # Render report
    lines = [
        "# Live Route Status",
        "",
        f"- Base URL: `{BASE}`",
        f"- Test org: `{org_id}`",
        "",
        "| Group | Route | Method | URL | HTTP Status | Note |",
        "|---|---|---:|---|---:|---|",
    ]
    for group, name, method, url, status, note in rows:
        lines.append(f"| {group} | {name} | {method} | `{url}` | {status} | {note} |")

    REPORT.write_text("\n".join(lines))
    print(f"Wrote {REPORT} with {len(rows)} rows")


if __name__ == "__main__":
    main()
