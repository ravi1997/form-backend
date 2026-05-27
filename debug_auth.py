from app.app import create_app
from models.User import User
import logging

app = create_app()
with app.app_context():
    logging.basicConfig(level=logging.INFO)
    print("Testing authentication for alice@hospital.org...")
    try:
        user = User.authenticate("alice@hospital.org", "SecurePass123!")
        if user:
            print(f"SUCCESS: Authenticated user {user.username}")
        else:
            print(
                "FAILURE: Authentication returned None (user not found, locked, or wrong password)"
            )
    except Exception as e:
        import traceback

        print(f"CRASH: Authentication failed with error: {str(e)}")
        traceback.print_exc()
