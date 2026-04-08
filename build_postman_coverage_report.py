import json
import re
from pathlib import Path


COLL = Path("postman_collection_merged.json")
OUT = Path("postman_coverage_report.md")

MOUNTS = {
    "routes/v1/auth_route.py": "/form/api/v1/auth",
    "routes/v1/user_route.py": "/form/api/v1/user",
    "routes/v1/project_route.py": "/form/api/v1/projects",
    "routes/v1/dashboard_route.py": "/form/api/v1/dashboards",
    "routes/v1/dashboard_settings_route.py": "/form/api/v1/dashboard-settings",
    "routes/v1/workflow_route.py": "/form/api/v1/workflows",
    "routes/v1/webhooks.py": "/form/api/v1/webhooks",
    "routes/v1/sms_route.py": "/form/api/v1/sms",
    "routes/v1/external_api_route.py": "/form/api/v1/external",
    "routes/v1/analytics_route.py": "/form/api/v1/analytics",
    "routes/v1/admin/system_settings_route.py": "/form/api/v1/admin/system-settings",
    "routes/v1/admin/env_config_route.py": "/form/api/v1/admin/env-config",
    "routes/v1/admin/system_route.py": "/form/api/v1/system",
    "routes/v1/view_route.py": "/form/api/v1/view",
    "routes/v1/form/form.py": "/form/api/v1/forms",
    "routes/v1/form/additional.py": "/form/api/v1/forms",
    "routes/v1/form/responses.py": "/form/api/v1/forms",
    "routes/v1/form/export.py": "/form/api/v1/forms",
    "routes/v1/form/validation.py": "/form/api/v1/forms",
    "routes/v1/form/analytics.py": "/form/api/v1/forms",
    "routes/v1/form/summarization.py": "/form/api/v1/forms",
    "routes/v1/form/library.py": "/form/api/v1/custom-fields",
    "routes/v1/form/translation.py": "/form/api/v1/forms/translations",
    "routes/v1/form/hooks.py": "/form/api/v1/forms",
    "routes/v1/form/files.py": "/form/api/v1/forms",
    "routes/v1/form/advanced_responses.py": "/form/api/v1/forms",
    "routes/v1/form/permissions.py": "/form/api/v1/forms",
    "routes/v1/form/expire.py": "/form/api/v1/forms",
    "routes/v1/form/nlp_search.py": "/form/api/v1/ai/search",
    "routes/v1/form/anomaly.py": "/form/api/v1/forms",
    "routes/v1/form/ai.py": "/form/api/v1/ai",
}


def normalize_path(path: str) -> str:
    path = path.split("?", 1)[0]
    path = path.replace("{{base_url}}", "")
    path = path.replace(":user_id", "<user_id>")
    path = path.replace(":project_id", "<project_id>")
    path = path.replace(":form_id", "<form_id>")
    path = path.replace(":dashboard_slug", "<slug>")
    path = path.replace(":section_id", "<section_id>")
    path = path.replace(":template_id", "<template_id>")
    path = path.replace(":question_id", "<question_id>")
    path = path.replace(":response_id", "<response_id>")
    path = path.replace(":job_id", "<job_id>")
    path = path.replace(":widget_id", "<widget_id>")
    path = path.replace(":workflow_id", "<workflow_id>")
    path = path.replace(":delivery_id", "<delivery_id>")
    path = path.replace(":hook_id", "<hook_id>")
    path = path.replace(":org_id", "<org_id>")
    path = path.replace(":employee_id", "<employee_id>")
    path = path.replace(":uhid", "<uhid>")
    path = path.replace(":filename", "<filename>")
    path = path.replace(":search_id", "<search_id>")
    path = path.replace("<string:", "<")
    path = re.sub(r"<([^>]+)>", r"<\1>", path)
    path = path.rstrip("/")
    return path


def code_routes():
    out = []
    for file_path, prefix in MOUNTS.items():
        txt = Path(file_path).read_text()
        for m in re.finditer(r'@\w+\.route\((.*?)\,\s*methods=\[(.*?)\]\)', txt, re.S):
            route = m.group(1).strip().strip('"\'')
            methods = [x.strip().strip('"\'') for x in m.group(2).split(",")]
            route = route.replace("<string:", "<").replace("<int:", "<").replace("<path:", "<")
            for method in methods:
                out.append((method, normalize_path(prefix + route), file_path))
    return out


def collection_routes():
    coll = json.loads(COLL.read_text())["collection"]
    out = []
    def walk(items, group):
        for it in items:
            if "request" in it:
                raw = it["request"]["url"]["raw"] if isinstance(it["request"]["url"], dict) else it["request"]["url"]
                out.append((group, it["name"], it["request"]["method"], normalize_path(raw)))
            if "item" in it:
                walk(it["item"], it.get("name", group))
    walk(coll["item"], "")
    return out


def main():
    c_routes = collection_routes()
    k_routes = code_routes()
    code_map = {(m, p): src for m, p, src in k_routes}
    code_set = {(m, p) for m, p, _ in k_routes}
    postman_keys = {(m, p) for _, _, m, p in c_routes}

    rows = []
    for group, name, method, path in c_routes:
        code_src = code_map.get((method, path))
        if (method, path) in code_set:
            status = "Matched"
            code_ref = code_src
        else:
            status = "Stale in Postman"
            code_ref = "—"
        rows.append((group, name, method, path, code_ref, status))

    missing = []
    for method, path, src in k_routes:
        if (method, path) not in postman_keys:
            missing.append((method, path, src))

    lines = [
        "# Postman Coverage Report",
        "",
        f"- Collection: `{COLL}`",
        "- Status meanings: `Matched` = present in both, `Stale in Postman` = in collection but no current code route, `Missing in Postman` = present in code but not in collection.",
        "",
        "| Group | Postman Item | Method | Postman URL | Code URL | Status |",
        "|---|---|---:|---|---|---|",
    ]
    for group, name, method, path, code_ref, status in rows:
        lines.append(f"| {group} | {name} | {method} | `{path}` | `{code_ref}` | {status} |")

    lines += [
        "",
        "## Missing In Postman",
        "",
        "| Method | Code URL | File |",
        "|---|---|---|",
    ]
    for method, path, src in missing:
        lines.append(f"| {method} | `{path}` | `{src}` |")

    lines += [
        "",
        "## Stale In Postman",
        "",
        "| Group | Postman Item | Method | Postman URL |",
        "|---|---|---:|---|",
    ]
    for group, name, method, path, code_ref, status in rows:
        if status == "Stale in Postman":
            lines.append(f"| {group} | {name} | {method} | `{path}` |")

    OUT.write_text("\n".join(lines))
    print(f"Wrote {OUT}")
    print(f"Matched: {sum(1 for r in rows if r[-1]=='Matched')}")
    print(f"Stale: {sum(1 for r in rows if r[-1]=='Stale in Postman')}")
    print(f"Missing: {len(missing)}")


if __name__ == "__main__":
    main()
