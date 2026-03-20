import os
import importlib.util
import json
from pydantic import BaseModel
from typing import Type

SCHEMA_DIR = "/home/ravi/workspace/docker/apps/form-backend/schemas"

def get_pydantic_models():
    models = {}
    for root, _, files in os.walk(SCHEMA_DIR):
        for file in files:
            if file.endswith(".py") and "__init__.py" not in file:
                module_name = f"schemas.{file[:-3]}"
                filepath = os.path.join(root, file)
                
                # Dynamic import
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)
                except Exception as e:
                    print(f"Skipping {module_name}: {e}")
                    continue
                
                for name, obj in vars(module).items():
                    if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
                        models[name] = obj
    return models

def generate_definitions():
    models = get_pydantic_models()
    definitions = {}
    for name, model in models.items():
        try:
             # Pydantic v2
             schema = model.model_json_schema()
             # Flasgger expects definitions to not have $schema and other keys if they are in the 'definitions' section
             if "$defs" in schema:
                 # Flatten $defs if they exist
                 for def_name, def_val in schema["$defs"].items():
                     definitions[def_name] = def_val
                 del schema["$defs"]
             
             # Clean up root schema
             for key in ["$schema", "$id"]:
                 if key in schema:
                     del schema[key]
             
             definitions[name] = schema
        except Exception as e:
            print(f"Error generating schema for {name}: {e}")
            
    return definitions

if __name__ == "__main__":
    import sys
    sys.path.append("/home/ravi/workspace/docker/apps/form-backend")
    defs = generate_definitions()
    print(json.dumps(defs, indent=2))
