# Skill: Write Tests

## Unit test template (service)

```python
# tests/unit/test_services/test_talent_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from app.services.talent_service import TalentService
from app.schemas.talent import TalentCreate

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    return db

@pytest.fixture
def service(mock_db):
    return TalentService(db=mock_db)

class TestTalentService:
    @pytest.mark.unit
    async def test_create_talent_success(self, service, mock_db):
        org_id = uuid4()
        payload = TalentCreate(name="Test Talent")
        talent = await service.create(payload, org_id=org_id)
        assert talent.name == "Test Talent"
        mock_db.add.assert_called_once()

    @pytest.mark.unit
    async def test_get_not_found_raises(self, service, mock_db):
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)
        with pytest.raises(ValueError, match="not found"):
            await service.get(talent_id=uuid4(), org_id=uuid4())
```

## Integration test template (endpoint)

```python
@pytest.mark.integration
async def test_list_requires_auth(client):
    resp = await client.get("/api/v1/talent")
    assert resp.status_code == 401

@pytest.mark.integration
async def test_create_validation_error(client, auth_headers):
    resp = await client.post("/api/v1/talent", json={"name": ""}, headers=auth_headers)
    assert resp.status_code == 422
```

## Tenant isolation test (critical)

```python
@pytest.mark.integration
async def test_cannot_access_other_org(client, org_a_headers, org_b_talent_id):
    resp = await client.get(f"/api/v1/talent/{org_b_talent_id}", headers=org_a_headers)
    assert resp.status_code == 404  # Not 403 — don't reveal existence
```

## conftest.py essentials

```python
@pytest.fixture(autouse=True)
def mock_settings():
    with patch("app.core.config.get_settings") as mock:
        mock.return_value.secret_key = "test-secret-key-minimum-32-chars-long"
        mock.return_value.supabase_jwt_secret = "test-jwt-secret"
        mock.return_value.app_env = "development"
        yield mock.return_value
```

## Running tests

```bash
pytest tests/unit/ -v
pytest tests/ --cov=app --cov-report=term-missing
pytest -m "unit" -v
pytest -k "test_talent" -v
```
