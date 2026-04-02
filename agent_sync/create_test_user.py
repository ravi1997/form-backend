import sys
import os
sys.path.append(os.getcwd())

from models.User import User
from mongoengine import connect
from config.settings import settings

connect(host=settings.MONGODB_URI)

try:
    user = User.objects(username="testuser_frontend").first()
    if not user:
        user = User(
            username="testuser_frontend",
            email="frontend@test.com",
            user_type="employee",
            is_active=True
        )
    user.set_password("TestPass123!")
    user.save()
    print("User testuser_frontend created/updated successfully.")
except Exception as e:
    print(f"Error: {e}")
