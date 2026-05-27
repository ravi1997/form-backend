"""
scripts/export_openapi.py — Export OpenAPI spec from the Flask app.

Boots the app, calls the flasgger spec endpoint, writes JSON + YAML.

Usage:
    python scripts/export_openapi.py
    make openapi
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs"
)


def run():
    from app import create_app

    app = create_app()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with app.test_client() as client:
        response = client.get("/mahasangraha/apispec_1.json")
        if response.status_code != 200:
            print(f"❌ Failed to get spec: HTTP {response.status_code}")
            sys.exit(1)

        spec = response.get_json()

    # Write JSON
    json_path = os.path.join(OUTPUT_DIR, "openapi_spec.json")
    with open(json_path, "w") as f:
        json.dump(spec, f, indent=2)
    print(f"✅ OpenAPI JSON written to: {json_path}")

    # Write YAML
    try:
        import yaml

        yaml_path = os.path.join(OUTPUT_DIR, "openapi.yaml")
        with open(yaml_path, "w") as f:
            yaml.dump(spec, f, default_flow_style=False, allow_unicode=True)
        print(f"✅ OpenAPI YAML written to: {yaml_path}")
    except ImportError:
        print("⚠  PyYAML not installed — skipping YAML export (pip install pyyaml)")

    # Print endpoint summary
    paths = spec.get("paths", {})
    print(f"\n📋 Total endpoints: {sum(len(v) for v in paths.values())}")
    print(f"   Paths: {len(paths)}")
    print(f"   Tags: {len(spec.get('tags', []))}")

    # Contract check
    missing = []
    for path in [
        "/mahasangraha/api/v1/auth/login",
        "/mahasangraha/api/v1/auth/request-otp",
        "/mahasangraha/api/v1/projects/{project_id}/forms/",
        "/mahasangraha/api/v1/user/profile",
    ]:
        if path not in paths:
            missing.append(path)

    if missing:
        print(f"\n⚠  Missing from spec ({len(missing)}):")
        for m in missing:
            print(f"   {m}")
    else:
        print("\n✅ Core contract endpoints present in spec.")


if __name__ == "__main__":
    run()
