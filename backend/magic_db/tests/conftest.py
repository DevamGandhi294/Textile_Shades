"""Tests run against a real PostgreSQL. Set TEST_DATABASE_URL to an EMPTY test database (it is wiped).

    TEST_DATABASE_URL=postgresql+psycopg://magic:magic@127.0.0.1:5432/magic_outline_test pytest magic_db/tests
"""
import os
import tempfile

import pytest

url = os.environ.get("TEST_DATABASE_URL")
if not url:
    pytest.skip("Set TEST_DATABASE_URL to run the database tests.", allow_module_level=True)
os.environ.update({
    "DATABASE_URL": url, "STORAGE_BACKEND": "local", "LOCAL_STORAGE_DIR": tempfile.mkdtemp(prefix="magic_db_"),
    "OTP_DEV_ECHO": "1", "PAYMENTS_MODE": "fake", "API_TOKEN": "", "DEV_LOGIN_PHONE": "", "OPENAI_API_KEY": "",
    "SECRET_KEY": "test-secret", "BILLING_CHECKS": "1",          # the tests check the limits
})
if os.environ.get("TEST_S3_ENDPOINT_URL"):          # e.g. MinIO from docker-compose: http://127.0.0.1:9000
    os.environ.update({"STORAGE_BACKEND": "s3", "S3_ENDPOINT_URL": os.environ["TEST_S3_ENDPOINT_URL"],
                       "S3_BUCKET": "magic-outline-test"})


@pytest.fixture(scope="session", autouse=True)
def database():
    from alembic import command

    from magic_db.__main__ import _alembic
    command.downgrade(_alembic(), "base")
    command.upgrade(_alembic(), "head")
    from magic_db import storage
    storage.ensure_bucket()
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from magic_db.standalone import app
    return TestClient(app)


def register(client, phone, password="secret123", **extra):
    body = {"phone": phone, "password": password, "owner_name": "Owner", "company_name": "Shop", **extra}
    return client.post("/api/auth/register", json=body)


def session_of(response):
    """The login cookie as a header, so one TestClient can act as several people."""
    token = response.cookies.get("mo_session")
    assert token, response.text
    return {"X-Session-Token": token}


def login(client, phone, name="Owner", business="Shop"):
    r = register(client, phone, owner_name=name, company_name=business)
    assert r.status_code == 201, r.text
    client.cookies.clear()
    return session_of(r)
