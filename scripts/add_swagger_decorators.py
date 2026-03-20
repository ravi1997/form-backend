import os
import re

ROUTE_DIR = "/home/ravi/workspace/docker/apps/form-backend/routes/v1"

# Regex to match a route decorator like @xyz_bp.route(...)
ROUTE_REGEX = re.compile(r'^@([a-zA-Z0-9_]+)\.route\(([^)]+)\)')

def process_file(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()
        
    has_swag_from_import = False
    for line in lines:
        if 'flasgger import swag_from' in line:
            has_swag_from_import = True
            break
            
    if not has_swag_from_import:
        # insert it after flask imports
        for idx, line in enumerate(lines):
            if 'from flask import' in line or 'import Blueprint' in line:
                lines.insert(idx + 1, 'from flasgger import swag_from\n')
                break

    new_lines = []
    i = 0
    modified = False
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)
        
        # Check if line is a route decorator
        match = ROUTE_REGEX.search(line)
        if match:
            # Check if next line is already swag_from or limit
            next_lines = "".join(lines[i+1:i+3])
            if 'swag_from' not in next_lines:
                # Get endpoint details to create a basic Swagger spec
                route_params = match.group(2)
                method = "GET"
                if "methods=" in route_params:
                    if "POST" in route_params: method = "POST"
                    elif "PUT" in route_params: method = "PUT"
                    elif "DELETE" in route_params: method = "DELETE"
                
                tags = "API"
                bp_name = match.group(1).replace('_bp', '').title()
                
                swagger_snippet = f'''@swag_from({{
    "tags": ["{bp_name}"],
    "responses": {{
        "200": {{"description": "Success"}}
    }}
}})
'''
                new_lines.append(swagger_snippet)
                modified = True
        i += 1
        
    if modified:
        with open(filepath, 'w') as f:
            f.writelines(new_lines)
        print(f"Updated {filepath}")

for root, _, files in os.walk(ROUTE_DIR):
    for file in files:
        if file.endswith("_route.py") and file != "auth_route.py":
            process_file(os.path.join(root, file))

print("Done injecting @swag_from decorators.")
