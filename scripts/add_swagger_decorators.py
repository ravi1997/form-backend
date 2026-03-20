import os
import re

# Update to include all .py files in routes/v1 recursively
ROUTE_DIR = "/home/ravi/workspace/docker/apps/form-backend/routes/v1"

# Regex to match a route decorator like @xyz_bp.route(...)
ROUTE_REGEX = re.compile(r'@([a-zA-Z0-9_]+)\.route\(([^)]+)\)')

# Regex to find potential schema usage in the function body
# Matches something like `UserCreateSchema(**data)` or `schema = FormUpdateSchema(...)`
SCHEMA_USAGE_REGEX = re.compile(r'([A-Z][a-zA-Z0-9]+Schema|[A-Z][a-zA-Z0-9]+Out)')

def process_file(filepath):
    print(f"Processing {filepath}...")
    with open(filepath, 'r') as f:
        lines = f.readlines()
        
    has_swag_from_import = False
    for line in lines:
        if 'flasgger import swag_from' in line:
            has_swag_from_import = True
            break
            
    # Track where to insert the import
    import_insert_idx = -1
    if not has_swag_from_import:
        for idx, line in enumerate(lines):
            if 'from flask import' in line or 'import Blueprint' in line or 'from . import' in line:
                import_insert_idx = idx + 1
                break

    new_lines = []
    i = 0
    modified = False
    
    # If we need to add the import but haven't found a place yet, put it at top (after docstring)
    if not has_swag_from_import and import_insert_idx == -1:
         import_insert_idx = 0
         # Skip docstring
         if len(lines) > 0 and lines[0].strip().startswith('"""'):
             for j in range(1, len(lines)):
                 if lines[j].strip().endswith('"""'):
                     import_insert_idx = j + 1
                     break

    while i < len(lines):
        line = lines[i]
        
        # Check if line is a route decorator
        match = ROUTE_REGEX.search(line)
        if match:
            # Check if swag_from is already in next few lines
            found_existing_idx = -1
            for j in range(i+1, min(i+10, len(lines))):
                if '@swag_from' in lines[j]:
                    found_existing_idx = j
                    break
            
            # Find the function body to look for schemas and docstrings
            function_body = ""
            function_start = -1
            for j in range(i+1, min(i+20, len(lines))):
                if lines[j].strip().startswith('def '):
                    function_start = j
                    # Collect lines of the function (rough heuristic)
                    for k in range(j+1, min(j+50, len(lines))):
                        function_body += lines[k]
                    break
            
            # Extract schemas used in the function
            found_schemas = SCHEMA_USAGE_REGEX.findall(function_body)
            # Remove duplicates while preserving order
            found_schemas = list(dict.fromkeys(found_schemas))
            
            # Find input and output schemas
            input_schema = None
            output_schema = None
            for s in found_schemas:
                if 'Create' in s or 'Update' in s:
                    input_schema = s
                elif 'Out' in s or 'Result' in s:
                    output_schema = s
            
            # Get endpoint details
            route_params = match.group(2)
            method = "GET"
            if "methods=" in route_params:
                if "POST" in route_params: method = "POST"
                elif "PUT" in route_params: method = "PUT"
                elif "DELETE" in route_params: method = "DELETE"
            
            bp_handle = match.group(1)
            tag_name = bp_handle.replace('_bp', '').replace('bp', '').strip('_').title()
            if not tag_name: tag_name = "API"
            
            summary = "Success"
            if function_start != -1:
                for k in range(function_start+1, min(function_start+5, len(lines))):
                    doc_match = re.search(r'"""([^"]+)"""', lines[k])
                    if doc_match:
                        summary = doc_match.group(1).strip().split('\n')[0]
                        break

            # Build the Swagger spec
            responses = {
                "200": {"description": summary}
            }
            if output_schema:
                responses["200"]["schema"] = {"$ref": f"#/definitions/{output_schema}"}
            
            parameters = []
            # Check if there are URL path parameters
            path_params = re.findall(r'<[^>]+:([^>]+)>', route_params) or re.findall(r'<([^>]+)>', route_params)
            for p in path_params:
                parameters.append({
                    "name": p,
                    "in": "path",
                    "type": "string",
                    "required": True
                })
            
            # Add input schema for POST/PUT
            if input_schema and method in ["POST", "PUT"]:
                parameters.append({
                    "name": "body",
                    "in": "body",
                    "schema": {"$ref": f"#/definitions/{input_schema}"}
                })

            import json
            swagger_dict = {
                "tags": [tag_name],
                "responses": responses
            }
            if parameters:
                swagger_dict["parameters"] = parameters
            
            swagger_snippet = f"@swag_from({json.dumps(swagger_dict, indent=4)})\n"
            
            if found_existing_idx != -1:
                # Update existing swag_from (by replacing the lines from @swag_from({ to }) )
                # This is tricky because it's multiline. 
                # For simplicity, let's just replace the whole block if it matches our previous format
                # or if it's just a simple one.
                # Actually, the user says "every route has errors", so I'll just OVERWRITE existing ones.
                
                # Find the end of the existing @swag_from block
                end_idx = found_existing_idx
                if 'swag_from({' in lines[found_existing_idx]:
                    for j in range(found_existing_idx, min(found_existing_idx+20, len(lines))):
                        if '})' in lines[j]:
                            end_idx = j
                            break
                
                # Replace the old block with the new one
                lines[found_existing_idx:end_idx+1] = [swagger_snippet]
                modified = True
                # Adjust i since we modified lines
                # we don't need to do much since we are using 'lines' and iterating with 'i'
                # but let's be careful. Actually i will be incremented in next loop.
            else:
                # Insert new swag_from after the route decorator
                new_lines.append(line)
                new_lines.append(swagger_snippet)
                modified = True
                i += 1
                continue
        
        new_lines.append(line)
        i += 1
        
    if modified:
        if not has_swag_from_import:
            new_lines.insert(import_insert_idx, 'from flasgger import swag_from\n')
            
        with open(filepath, 'w') as f:
            f.writelines(new_lines)
        print(f"Updated {filepath}")

# Process all files in routes/v1
for root, _, files in os.walk(ROUTE_DIR):
    for file in files:
        if file.endswith(".py") and "__init__.py" not in file:
            process_file(os.path.join(root, file))

print("Done injecting/updating @swag_from decorators.")
