import os

import pytest


os.environ["DATABASE_URL"] = "sqlite:///./data/test_gateway.db"
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["MCP_API_KEY"] = "test-mcp-key"
os.environ["SECRET_ENCRYPTION_KEY"] = "test-only-encryption-key"
os.environ["MCP_ALLOWED_HOSTS"] = "localhost:*,127.0.0.1:*,testserver:*"
os.environ["MCP_ALLOWED_ORIGINS"] = "http://localhost:5173"


@pytest.fixture(autouse=True)
def clean_database():
    from app.database import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(scope="session")
def api_client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client

