# Testing Strategies

**Purpose:** Documentation for testing strategies, unit testing, integration testing, and end-to-end testing.

**Scope:** Testing strategy, unit testing, integration testing, end-to-end testing, test coverage, and test automation.

---

## Overview

This document outlines the testing strategy for the RIDP Form Platform, ensuring comprehensive test coverage across unit, integration, and end-to-end tests.

**Target Audience:** Backend developers, QA engineers, DevOps engineers

---

## Testing Pyramid

```
           ┌─────────┐
           │   E2E     │
           │  Tests   │
           └─────────┘
         /           \
        /             \
    ┌──────┐      ┌──────┐
    │Integration│   │ Unit  │
    │  Tests │   │ Tests │
    └──────┘      └──────┘
```

### Test Levels

| Level | Scope | Speed | Coverage |
|-------|-------|-------|----------|
| Unit Tests | Single function/class | Fast | 70-80% |
| Integration Tests | Multiple components | Medium | 20-25% |
| E2E Tests | Full system | Slow | 5-10% |

---

## Unit Testing

### Testing Framework

**pytest** with **pytest-cov** for coverage.

### Configuration

```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = --verbose --cov=services --cov=routes --cov-report=term-missing --cov-report=html
```

### Unit Test Examples

**Service Layer Tests:**

```python
# tests/test_form_service.py
import pytest
from unittest.mock import Mock, patch
from services.form_service import FormService

class TestFormService:
    def test_create_form_success(self):
        """Test successful form creation."""
        # Arrange
        schema = Mock()
        schema.name = "Test Form"
        schema.description = "Test Description"

        # Act
        form = FormService.create(schema)

        # Assert
        assert form.name == "Test Form"
        assert form.description == "Test Description"
        assert form.organization_id is not None

    def test_create_form_invalid_schema(self):
        """Test form creation with invalid schema."""
        # Arrange
        schema = Mock()
        schema.name = ""  # Invalid: empty name

        # Act & Assert
        with pytest.raises(ValueError, match="Name is required"):
            FormService.create(schema)
```

**Validation Tests:**

```python
# tests/test_password_validator.py
import pytest
from utils.password_validator import password_validator, PasswordStrength

class TestPasswordValidator:
    def test_too_short_password(self):
        """Test password too short."""
        result = password_validator.validate("short")

        assert result.is_valid == False
        assert "at least 12 characters" in result.errors[0]

    def test_weak_password(self):
        """Test weak password."""
        result = password_validator.validate("password123")

        assert result.strength == PasswordStrength.WEAK

    def test_strong_password(self):
        """Test strong password."""
        result = password_validator.validate("MyP@ssw0rd!")

        assert result.is_valid == True
        assert result.strength == PasswordStrength.STRONG
```

**File Validation Tests:**

```python
# tests/test_file_validator.py
import pytest
from utils.file_validator import validate_upload, FileUploadError
from werkzeug.datastructures import FileStorage

class TestFileValidator:
    def test_block_malicious_extension(self):
        """Test blocking malicious file extension."""
        # Create malicious file
        file = FileStorage(
            stream=io.BytesIO(b"test"),
            filename="malicious.php"
        )

        # Act & Assert
        with pytest.raises(FileUploadError):
            validate_upload(file)

    def test_mime_type_spoofing(self):
        """Test MIME type spoofing prevention."""
        # Create PHP file with .jpg extension
        file = FileStorage(
            stream=io.BytesIO(b"<?php echo 'hacked'; ?>"),
            filename="malicious.php.jpg"
        )

        # Act & Assert
        with pytest.raises(FileUploadError):
            validate_upload(file)
```

---

## Integration Testing

### MongoDB + Redis Testcontainers

**Configuration:**

```python
# tests/conftest.py
import pytest
from testcontainers.mongodb import MongoDbContainer
from testcontainers.redis import RedisContainer

@pytest.fixture(scope="session")
def mongodb_container():
    """MongoDB test container."""
    with MongoDbContainer("mongo:6.0") as mongo:
        yield mongo

@pytest.fixture(scope="session")
def redis_container():
    """Redis test container."""
    with RedisContainer("redis:7") as redis:
        yield redis

@pytest.fixture(scope="session")
def app(mongodb_container, redis_container):
    """Test application with testcontainers."""
    # Configure test environment
    import os
    os.environ["APP_ENV"] = "testing"
    os.environ["MONGODB_URI"] = mongodb_container.get_connection_url()
    os.environ["REDIS_HOST"] = redis_container.get_container_host_ip()
    os.environ["REDIS_PORT"] = redis_container.get_container_port("6379")

    # Create test app
    from app import create_app
    app = create_app()

    yield app
```

### Integration Test Examples

**API Endpoint Tests:**

```python
# tests/test_form_route.py
import pytest
import json
from flask_jwt_extended import create_access_token

class TestFormRoute:
    def test_create_form_success(self, app):
        """Test successful form creation."""
        with app.test_client() as client:
            # Create user and token
            user = create_test_user()
            token = create_access_token(identity=str(user.id))

            # Act
            response = client.post(
                "/form/api/v1/forms",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": "Test Form",
                    "description": "Test Description",
                    "status": "draft"
                }
            )

            # Assert
            assert response.status_code == 201
            data = json.loads(response.data)
            assert data["success"] == True
            assert data["data"]["name"] == "Test Form"

    def test_create_form_validation_error(self, app):
        """Test form creation with validation error."""
        with app.test_client() as client:
            # Create user and token
            user = create_test_user()
            token = create_access_token(identity=str(user.id))

            # Act
            response = client.post(
                "/form/api/v1/forms",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": "",  # Invalid: empty name
                    "description": "Test Description",
                    "status": "draft"
                }
            )

            # Assert
            assert response.status_code == 400
            data = json.loads(response.data)
            assert data["success"] == False
            assert "validation" in str(data["error"]).lower()
```

**Database Tests:**

```python
# tests/test_form_model.py
import pytest
from models.form import Form
from datetime import datetime

class TestFormModel:
    def test_form_creation(self, app):
        """Test form model creation."""
        with app.app_context():
            # Arrange
            form = Form(
                name="Test Form",
                description="Test Description",
                organization_id="test_org",
                status="draft",
                is_deleted=False
            )

            # Act
            form.save()

            # Assert
            assert form.id is not None
            assert form.name == "Test Form"
            assert form.organization_id == "test_org"

    def test_form_tenant_isolation(self, app):
        """Test form tenant isolation."""
        with app.app_context():
            # Create forms for different orgs
            form1 = Form(
                name="Form 1",
                organization_id="org1",
                status="draft"
            )
            form1.save()

            form2 = Form(
                name="Form 2",
                organization_id="org2",
                status="draft"
            )
            form2.save()

            # Act - Query with org1 context
            from flask import g
            g.organization_id = "org1"

            forms = Form.objects()

            # Assert
            assert len(forms) == 1
            assert forms[0].id == form1.id
```

---

## End-to-End Testing

### E2E Test Framework

**Cypress** or **Playwright** for frontend + backend testing.

### Example E2E Test

```javascript
// cypress/e2e/form_workflow.cy.js
describe('Form Workflow', () => {
    beforeEach(() => {
        cy.login('user@example.com', 'password123');
    });

    it('creates and submits a form', () => {
        // Navigate to forms page
        cy.visit('/forms');

        // Click create form button
        cy.contains('button', 'Create Form').click();

        // Fill in form details
        cy.get('[name="name"]').type('Test Form');
        cy.get('[name="description"]').type('Test Description');

        // Save form
        cy.contains('button', 'Save').click();

        // Navigate to form
        cy.url().should('include', '/forms/');

        // Open form
        cy.contains('Test Form').click();

        // Submit response
        cy.contains('button', 'Submit').click();

        // Verify submission
        cy.contains('Response submitted successfully').should('be.visible');
    });
});
```

---

## Test Coverage

### Coverage Goals

**Minimum Coverage:**

| Component | Target Coverage |
|-----------|-----------------|
| Services | 80% |
| Routes | 70% |
| Models | 80% |
| Utils | 90% |
| Middleware | 70% |

### Coverage Configuration

```ini
# pytest.ini
[pytest]
addopts = --cov=services --cov=routes --cov=models --cov=utils --cov=middleware
        --cov-report=term-missing
        --cov-report=html
        --cov-fail-under=70
```

### Running Coverage

```bash
# Run all tests with coverage
pytest --cov=services --cov=routes --cov=models --cov=utils

# Generate HTML report
pytest --cov-report=html

# Generate terminal report
pytest --cov-report=term
```

---

## Test Automation

### CI/CD Integration

**GitHub Actions Example:**

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      - mongo
      - redis

    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-mock

      - name: Run tests
        run: |
          pytest --cov=services --cov=routes --cov=models --cov=utils
          --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

---

## Best Practices

### 1. Write Isolated Tests

```python
# CORRECT - Isolated test
def test_create_form():
    form = create_form("Test Form")
    assert form.name == "Test Form"

# WRONG - Dependent on other tests
# test_create_form() requires test_login() to run first
```

### 2. Use Descriptive Test Names

```python
# CORRECT - Descriptive
def test_create_form_with_valid_data_creates_form_successfully():
    pass

def test_create_form_with_duplicate_name_returns_error():
    pass

# WRONG - Generic names
def test_create_form_1():
    pass

def test_create_form_2():
    pass
```

### 3. Test Both Success and Failure Cases

```python
# CORRECT - Test both cases
def test_create_form_success():
    pass

def test_create_form_validation_error():
    pass

# WRONG - Only test success
def test_create_form():
    pass
```

### 4. Use Fixtures for Setup

```python
# CORRECT - Use fixtures
@pytest.fixture
def authenticated_user():
    return create_test_user()

# WRONG - Setup in every test
def test_something():
    user = create_test_user()  # Repeated setup
```

### 5. Mock External Dependencies

```python
# CORRECT - Mock external dependencies
@patch('services.form_service.external_api_call')
def test_form_publish_with_external_api_success(mock_api):
    mock_api.return_value = {"status": "success"}
    result = form_service.publish(form_id)
    assert result == "success"

# WRONG - Don't mock external dependencies
# Tests depend on external API
```

---

## Testing Strategy

### Test Data Management

**Factory Pattern:**

```python
# tests/factories.py
import factory
from models.form import Form
from models.user import User

class UserFactory(factory.Factory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password = factory.PostGenerationMethodCall(
        lambda obj, n, ctx, **kwargs: obj.set_password("Password123!")
    )

class FormFactory(factory.Factory):
    class Meta:
        model = Form

    name = factory.Faker("sentence")
    description = factory.Faker("paragraph")
    organization_id = "test_org"
    status = "draft"
```

**Usage:**

```python
# tests/test_form_service.py
def test_create_form():
    # Create test data with factory
    user = UserFactory()
    form = FormFactory(organization_id=user.organization_id)

    result = form_service.create(form)

    assert result.name == form.name
```

---

## References

- [pytest Documentation](https://docs.pytest.org/)
- [Testcontainers Documentation](https://testcontainers-python.readthedocs.io/)
- [Flask Testing Documentation](https://flask.palletsprojects.com/Flask/1.1.x/testing/)
- [Cypress Documentation](https://docs.cypress.io/)
- [Playwright Documentation](https://playwright.dev/)
