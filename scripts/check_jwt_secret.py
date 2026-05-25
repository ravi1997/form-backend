#!/usr/bin/env python3
import sys
import re

DEFAULT_INSECURE_SECRET = "super-secret-key-change-me"


def check_files():
    found_insecure = False
    # Check arguments passed by pre-commit (list of changed files)
    files_to_check = sys.argv[1:]

    # Fallback to defaults if no arguments provided
    if not files_to_check:
        files_to_check = [".env", "config/settings.py"]

    for file_path in files_to_check:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                # Check for direct occurrences of the default secret
                if DEFAULT_INSECURE_SECRET in content:
                    # In config/settings.py, defining it as a default fallback is allowed for testing/development,
                    # but only if it's the class definition setting it, not in an active configuration file (.env).
                    # Let's enforce that if it is in .env, it's blocked.
                    if ".env" in file_path:
                        print(
                            f"❌ CRITICAL SECURITY ERROR: Found insecure default JWT secret in {file_path}"
                        )
                        print(
                            f"Please change JWT_SECRET_KEY in {file_path} to a secure random value."
                        )
                        found_insecure = True
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

    if found_insecure:
        sys.exit(1)
    print("✅ JWT Secret security check passed.")
    sys.exit(0)


if __name__ == "__main__":
    check_files()
