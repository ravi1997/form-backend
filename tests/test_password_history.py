import pytest
import bcrypt
from models.User import User
from services.user_service import UserService
from schemas.user import UserCreateSchema, UserUpdateSchema
from utils.exceptions import ValidationError

def test_password_policy_substrings(app, db_connection):
    service = UserService()
    
    # Try creating user where password contains username
    with pytest.raises(ValidationError) as exc:
        schema = UserCreateSchema(
            username="alice",
            email="alice@example.com",
            user_type="employee",
            organization_id="org-1",
            roles=["admin"],
            password="alice_is_cool_753"
        )
        service.create(schema)
    assert "username" in str(exc.value).lower()

    # Try creating user where password contains email (use different username to avoid triggering username check first)
    with pytest.raises(ValidationError) as exc:
        schema = UserCreateSchema(
            username="alice_new",
            email="bob@example.com",
            user_type="employee",
            organization_id="org-1",
            roles=["admin"],
            password="bob@example.com_753"
        )
        service.create(schema)
    assert "email" in str(exc.value).lower()

def test_password_history_prevent_matches(app, db_connection):
    service = UserService()
    
    # 1. Create a user with a valid complex password (no sequential numbers like 123)
    schema = UserCreateSchema(
        username="alice_history",
        email="alice_history@example.com",
        user_type="employee",
        organization_id="org-1",
        roles=["admin"],
        password="ValidPassword975!"
    )
    user_schema = service.create(schema)
    
    # Verify first history entry
    user_doc = User.objects(id=user_schema.id).get()
    print("INITIAL PASSWORD HISTORY:", user_doc.password_history)
    assert len(user_doc.password_history) == 1
    
    # 2. Update to a new password
    update_schema = UserUpdateSchema(
        password="NewPassword864!"
    )
    service.update(user_schema.id, update_schema)
    
    user_doc.reload()
    print("AFTER FIRST UPDATE PASSWORD HISTORY:", user_doc.password_history)
    assert len(user_doc.password_history) == 2
    
    # 3. Try to update back to the first password (which is in history)
    with pytest.raises(ValidationError) as exc:
        update_schema_dup = UserUpdateSchema(
            password="ValidPassword975!"
        )
        service.update(user_schema.id, update_schema_dup)
    assert "last 5" in str(exc.value).lower()
