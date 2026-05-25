"""
scripts/contract_test.py — Route contract validation.

Compares registered Flask routes against the expected frontend API contract.
Exits non-zero if any contract endpoint is missing from the running app.

Usage:
    python scripts/contract_test.py
    make contract-test
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

# These are the endpoints the Flutter frontend currently calls.
# Update this list whenever frontend api_endpoints.dart is changed.
REQUIRED_ROUTES = [
    # Auth
    ("POST", "/form/api/v1/auth/register"),
    ("POST", "/form/api/v1/auth/login"),
    ("POST", "/form/api/v1/auth/request-otp"),
    ("POST", "/form/api/v1/auth/otp/request"),   # alias
    ("POST", "/form/api/v1/auth/otp/verify"),     # alias
    ("POST", "/form/api/v1/auth/refresh"),
    ("POST", "/form/api/v1/auth/logout"),
    ("POST", "/form/api/v1/auth/revoke-all"),
    # Users
    ("GET",  "/form/api/v1/user/profile"),
    ("PUT",  "/form/api/v1/user/profile"),
    ("POST", "/form/api/v1/user/change-password"),
    ("GET",  "/form/api/v1/user/users"),
    # Forms
    ("GET",  "/form/api/v1/forms/"),
    ("POST", "/form/api/v1/forms/"),
    ("GET",  "/form/api/v1/forms/<id>"),
    ("PUT",  "/form/api/v1/forms/<id>"),
    ("DELETE", "/form/api/v1/forms/<id>"),
    ("POST", "/form/api/v1/forms/<id>/publish"),
    ("POST", "/form/api/v1/forms/<id>/clone"),
    # Responses
    ("GET",  "/form/api/v1/forms/<id>/responses"),
    ("POST", "/form/api/v1/forms/<id>/responses"),
    # Dashboard
    ("GET",  "/form/api/v1/dashboards/<slug>"),
    ("POST", "/form/api/v1/dashboards/"),
    # Analytics
    ("GET",  "/form/api/v1/forms/<id>/analytics/summary"),
    # SMS
    ("POST", "/form/api/v1/sms/single"),
    ("GET",  "/form/api/v1/sms/health"),
    # Health
    ("GET",  "/form/health"),
]


def normalise(rule: str) -> str:
    """Replace Flask variable segments with <id> for comparison."""
    import re
    return re.sub(r"<[^>]+>", "<id>", rule)


def run():
    app = create_app()
    registered = set()
    for rule in app.url_map.iter_rules():
        for method in rule.methods or []:
            if method in ("HEAD", "OPTIONS"):
                continue
            registered.add((method, normalise(rule.rule)))

    missing = []
    for method, path in REQUIRED_ROUTES:
        if (method, normalise(path)) not in registered:
            missing.append(f"  {method:6s} {path}")

    if missing:
        print(f"\n❌ Contract violations — {len(missing)} missing endpoint(s):\n")
        for m in missing:
            print(m)
        print()
        sys.exit(1)
    else:
        print(f"\n✅ All {len(REQUIRED_ROUTES)} contract endpoints are registered.\n")


if __name__ == "__main__":
    run()
