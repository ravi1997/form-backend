import json
import uuid

with open('postman_collection.json', 'r') as f:
    coll = json.load(f)

# Global variables for tracking fixes
fixes = []

def add_script(item, script_type, exec_lines):
    if "event" not in item:
        item["event"] = []
    
    # Check if script type exists
    for ev in item["event"]:
        if ev["listen"] == script_type:
            ev["script"]["exec"] = exec_lines
            return
            
    item["event"].append({
        "listen": script_type,
        "script": {
            "type": "text/javascript",
            "exec": exec_lines
        }
    })

def fix_request(item, path=""):
    global fixes
    
    if "request" not in item:
        if "item" in item:
            for sub_item in item["item"]:
                fix_request(sub_item, path + "/" + item["name"])
        return
        
    req = item["request"]
    method = req.get("method", "GET").upper()
    url = req.get("url", {}).get("raw", "") if isinstance(req.get("url"), dict) else req.get("url", "")
    name = item.get("name", "")
    
    issue_found = False
    body_updated = False
    pre_added = False
    test_added = False
    inference_used = False
    notes = []
    
    # --- 1. Fix Bodies ---
    body = req.get("body", {}).get("raw", "")
    
    # Remove bodies from GET/DELETE or empty "{}"
    if method in ["GET", "DELETE"]:
        if "body" in req:
            issue_found = True
            del req["body"]
            body_updated = True
            notes.append(f"Removed body from {method} request")

    # Upgrade POST/PUT bodies
    if method in ["POST", "PUT", "PATCH"]:
        if not body or body.strip() == "{}" or "typing.Literal" in body or "string" in body:
            issue_found = True
            new_body = {}
            
            # Auth
            if "auth/login" in url:
                new_body = {
                    "identifier": "admin@example.com",
                    "password": "Password123!"
                }
            elif "auth/register" in url:
                new_body = {
                    "username": "johndoe",
                    "email": "{{created_email}}",
                    "password": "Password123!",
                    "user_type": "employee",
                    "mobile": "1234567890"
                }
            elif "auth/request-otp" in url:
                new_body = {"email": "admin@example.com"}
                
            # Forms
            elif "/forms/" in url and "forms/:form_id" not in url and method == "POST":
                # Create Form
                new_body = {
                    "title": "Patient Intake Form",
                    "slug": "{{form_slug}}",
                    "organization_id": "org_123",
                    "description": "Form for new patient registration.",
                    "status": "draft",
                    "ui_type": "flex",
                    "supported_languages": ["en", "es"]
                }
            elif "forms/:form_id/permissions" in url:
                new_body = {
                    "user_id": "user_789",
                    "role": "editor",
                    "can_view": True,
                    "can_edit": True
                }
                
            # Dashboards & Widgets
            elif "dashboards" in url and method == "POST":
                new_body = {
                    "title": "Main KPI Dashboard",
                    "slug": "main-kpi-dashboard",
                    "organization_id": "org_123",
                    "layout_type": "grid"
                }
            elif "dashboard/widgets" in url and "positions" not in url:
                new_body = {
                    "title": "Submission Trend",
                    "widget_type": "line_chart",
                    "data_source": "submissions",
                    "config": {"time_range": "last_30_days"}
                }
            elif "dashboard/widgets/positions" in url:
                new_body = {
                    "positions": {
                        "{{widget_id}}": {"x": 0, "y": 0, "w": 2, "h": 2}
                    }
                }
                
            # AI
            elif "ai/forms/:form_id/summarize" in url:
                new_body = {
                    "response_ids": [],
                    "strategy": "hybrid",
                    "format": "bullet_points"
                }
            elif "ai/forms/:form_id/semantic-search" in url:
                new_body = {
                    "query": "What are the main complaints about product quality?",
                    "similarity_threshold": 0.75
                }
            elif "ai/forms/:form_id/search-history" in url and method == "POST":
                new_body = {
                    "query": "quality complaints",
                    "results_count": 5
                }
            elif "ai/forms/:form_id/executive-summary" in url:
                new_body = {
                    "audience": "leadership",
                    "tone": "formal",
                    "max_points": 5
                }
            elif "ai/forms/:form_id/theme-summary" in url:
                new_body = {"themes": ["delivery", "pricing"]}
            elif "ai/forms/:form_id/responses/:response_id/analyze" in url:
                new_body = {"analysis_type": "sentiment"}
            elif "ai/forms/:form_id/responses/:response_id/moderate" in url:
                new_body = {"strictness": "high"}
            elif "ai/cross-analysis" in url:
                new_body = {"form_ids": ["{{form_id}}"], "metrics": ["completion_rate"]}
            elif "ai/generate" in url:
                new_body = {"prompt": "Generate a patient feedback form", "industry": "healthcare"}
            elif "ai/suggestions" in url:
                new_body = {"context": "Question about medical history", "count": 3}
                
            # External & SMS
            elif "sms/notify" in url:
                new_body = {"mobile": "9899378106", "title": "Alert", "body": "Please review form."}
            elif "sms/otp" in url:
                new_body = {"mobile": "9899378106", "otp": "123456"}
            elif "sms/single" in url:
                new_body = {"mobile": "9899378106", "message": "Test SMS"}
            elif "external/mail" in url:
                new_body = {"to": "test@example.com", "subject": "Welcome", "body": "Hello!"}
            elif "external/sms" in url:
                new_body = {"to": "9899378106", "message": "External ping"}
                
            # Admin & Users
            elif "admin/users" in url and method in ["POST", "PUT"]:
                new_body = {
                    "username": "adminuser",
                    "email": "admin2@example.com",
                    "user_type": "employee",
                    "roles": ["admin"]
                }
            elif "user/users" in url and method in ["POST", "PUT"]:
                new_body = {
                    "username": "updateduser",
                    "email": "updated@example.com",
                    "user_type": "general"
                }
                
            # Workflows
            elif "workflows" in url and method in ["POST", "PUT"]:
                new_body = {
                    "name": "Approval Workflow",
                    "description": "Standard multi-step approval.",
                    "steps": [{"step_type": "approval", "approver_roles": ["manager"]}]
                }
                
            # Custom fields
            elif "custom-fields" in url and method == "POST":
                new_body = {
                    "label": "Medical History",
                    "field_type": "textarea",
                    "help_text": "List any prior surgeries.",
                    "variable_name": "medical_history",
                    "is_required": True
                }
                
            # Templates
            elif "/templates/" in url and method == "POST":
                new_body = {
                    "name": "Standard Checkup Template",
                    "structure": "JSON structure string or dict here",
                    "tags": ["healthcare", "checkup"]
                }
                
            if new_body:
                req["body"] = {
                    "mode": "raw",
                    "raw": json.dumps(new_body, indent=4),
                    "options": {"raw": {"language": "json"}}
                }
                body_updated = True
                inference_used = True
                notes.append("Inferred realistic payload")
                
                # Add descriptions indicating inference
                if "description" not in req:
                    req["description"] = ""
                req["description"] += "\n\n*Note: Request body inferred based on realistic API usage (x_inference_level: inferred).*"

    # --- 2. Pre-request Scripts ---
    pre_script = []
    if "auth/register" in url:
        pre_script.append('pm.environment.set("created_email", "test.user." + Date.now() + "@example.com");')
    elif method == "POST" and "forms" in url and not ":form_id" in url:
        pre_script.append('pm.environment.set("form_slug", "form-" + Date.now());')
        
    if req.get("auth") or (req.get("header") and any(h.get("key") == "Authorization" for h in req.get("header"))):
        pre_script.append('if (!pm.environment.get("access_token")) { console.warn("Missing access_token!"); }')
        
    if pre_script:
        add_script(item, "prerequest", pre_script)
        pre_added = True

    # --- 3. Test Scripts ---
    test_script = [
        'pm.test("Status code is 2xx", function () {',
        '    pm.expect(pm.response.code).to.be.oneOf([200, 201, 202, 204]);',
        '});'
    ]
    
    if "auth/login" in url:
        test_script.extend([
            'if (pm.response.code === 200) {',
            '    let jsonData = pm.response.json();',
            '    if (jsonData.data && jsonData.data.access_token) {',
            '        pm.environment.set("access_token", jsonData.data.access_token);',
            '        pm.environment.set("refresh_token", jsonData.data.refresh_token);',
            '    }',
            '}'
        ])
    elif "auth/register" in url:
        test_script.extend([
            'if (pm.response.code === 201) {',
            '    let jsonData = pm.response.json();',
            '    if (jsonData.data && jsonData.data.user) {',
            '        pm.environment.set("user_id", jsonData.data.user.id);',
            '    }',
            '}'
        ])
    elif "forms/" in url and method == "POST" and "ai" not in url:
        test_script.extend([
            'if (pm.response.code === 201) {',
            '    try { let jsonData = pm.response.json(); if(jsonData.data && jsonData.data.id) pm.environment.set("form_id", jsonData.data.id); } catch(e) {}',
            '}'
        ])
    elif "dashboards/" in url and method == "POST":
        test_script.extend([
            'if (pm.response.code === 201) {',
            '    try { let jsonData = pm.response.json(); if(jsonData.data && jsonData.data.id) pm.environment.set("dashboard_id", jsonData.data.id); } catch(e) {}',
            '}'
        ])
    elif "dashboard/widgets" in url and method == "POST":
        test_script.extend([
            'if (pm.response.code === 201) {',
            '    try { let jsonData = pm.response.json(); if(jsonData.data && jsonData.data.id) pm.environment.set("widget_id", jsonData.data.id); } catch(e) {}',
            '}'
        ])
    elif "templates/" in url and method == "POST":
        test_script.extend([
            'if (pm.response.code === 201) {',
            '    try { let jsonData = pm.response.json(); if(jsonData.data && jsonData.data.id) pm.environment.set("template_id", jsonData.data.id); } catch(e) {}',
            '}'
        ])
        
    add_script(item, "test", test_script)
    test_added = True
    
    fixes.append({
        "name": name,
        "method": method,
        "issue_found": issue_found,
        "body_updated": body_updated,
        "pre_added": pre_added,
        "test_added": test_added,
        "inference_used": inference_used,
        "notes": ", ".join(notes) if notes else "Standard script updates"
    })

# Run over all
for i in coll.get("item", []):
    fix_request(i)

with open('postman_collection_updated.json', 'w') as f:
    json.dump(coll, f, indent=4)
    
with open('fixes_report.json', 'w') as f:
    json.dump(fixes, f, indent=4)
