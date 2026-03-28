import json
import re

def parse_md_to_postman(md_file_path):
    postman_collection = {
        "info": {
            "name": "Form Backend Full Collection",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        },
        "item": []
    }
    
    with open(md_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Split by folders (## Section)
    sections = re.split(r'\n## ', content)
    
    # Process sections
    for section in sections[1:]:
        lines = section.split('\n')
        folder_name = re.sub(r'[^\w\s-]', '', lines[0]).strip()
        folder = {
            "name": folder_name,
            "item": []
        }
        
        # Split by APIs (### Method Path)
        apis = re.split(r'\n### \`([A-Z, ]+)\`\s+`([^`]+)`', section)
        
        # The first chunk is preamble, subsequent chunks are method, path, content
        for i in range(1, len(apis), 3):
            method_str = apis[i]
            path = apis[i+1]
            api_content = apis[i+2]
            
            # Use the first method if multiple (like PUT, POST)
            primary_method = method_str.split(',')[0].strip()
            
            # Path formatting for Postman (replace <var> with :var)
            raw_url = path.replace('<', ':').replace('>', '')
            url_parts = raw_url.strip('/').split('/')
            
            # Variables for url
            variables = []
            for part in url_parts:
                if part.startswith(':'):
                    variables.append({"key": part[1:], "value": ""})
            
            # Request Body
            body = None
            body_match = re.search(r'```json\n(.*?)\n```', api_content, re.DOTALL)
            if body_match and "Payload schema not explicitly defined" not in body_match.group(1):
                raw_json = body_match.group(1).strip()
                try:
                    # Clean up the JSON if it has comments (which route.md has)
                    clean_json = re.sub(r'//.*', '', raw_json)
                    parsed_json = json.loads(clean_json)
                    body = {
                        "mode": "raw",
                        "raw": json.dumps(parsed_json, indent=4),
                        "options": {
                            "raw": {
                                "language": "json"
                            }
                        }
                    }
                except:
                    pass
            
            # Build Item
            item = {
                "name": f"{primary_method} {path}",
                "request": {
                    "method": primary_method,
                    "header": [
                        {
                            "key": "Authorization",
                            "value": "Bearer {{access_token}}",
                            "type": "text"
                        }
                    ] if "Requires Authentication" in api_content else [],
                    "url": {
                        "raw": "{{base_url}}" + raw_url,
                        "host": [
                            "{{base_url}}"
                        ],
                        "path": url_parts,
                        "variable": variables
                    }
                },
                "response": []
            }
            if body:
                item["request"]["body"] = body
                
            folder["item"].append(item)
            
        if folder["item"]:
            postman_collection["item"].append(folder)
            
    with open('postman_collection.json', 'w', encoding='utf-8') as f:
        json.dump(postman_collection, f, indent=4)
        
    print("Collection generated at postman_collection.json")

    env = {
        "id": "1",
        "name": "Form Backend Local Env",
        "values": [
            {
                "key": "base_url",
                "value": "http://localhost:8051",
                "type": "default",
                "enabled": True
            },
            {
                "key": "access_token",
                "value": "",
                "type": "default",
                "enabled": True
            }
        ]
    }
    with open('postman_environment.json', 'w', encoding='utf-8') as f:
        json.dump(env, f, indent=4)
        
if __name__ == "__main__":
    parse_md_to_postman("route.md")
