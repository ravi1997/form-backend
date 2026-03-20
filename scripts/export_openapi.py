import json
from app import create_app
import os

def export_swagger_spec(output_file="openapi_spec.json"):
    """
    Spins up the Flask active application context to resolve all @swag_from definitions 
    and dumps a standalone OpenAPI/Swagger JSON artifact.
    This artifact is strictly intended for generating Client SDKs 
    (e.g., via `openapi-generator-cli generate -i openapi_spec.json -g typescript-axios`).
    """
    app = create_app(testing=True)
    with app.test_client() as client:
        # Request the automatically rendered flasgger spec
        response = client.get('/apispec_1.json')
        if response.status_code == 200:
            os.makedirs("docs", exist_ok=True)
            with open(f"docs/{output_file}", "w") as f:
                json.dump(response.json, f, indent=2)
            print(f"✅ Extracted API Contract to docs/{output_file}")
            print("To generate a TypeScript SDK:")
            print(f"npx @openapitools/openapi-generator-cli generate -i docs/{output_file} -g typescript-axios -o sdk/ts")
        else:
            print(f"❌ Failed to extract API Spec. Status {response.status_code}")

if __name__ == "__main__":
    export_swagger_spec()
