# tests/conftest.py
import os
import pytest
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DISCUSS_ADMIN_USER"] = "admin"
os.environ["DISCUSS_ADMIN_PASS"] = "secret"

from server.db import Base, get_db
from server import models  # noqa
from server.main import app


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = TestingSession()

    # Seed default admin so admin-auth endpoints work in tests
    from server.models import AdminUser
    from server.auth import hash_password
    from datetime import datetime
    session.add(AdminUser(
        username="admin",
        password_hash=hash_password("secret"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    ))
    session.commit()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
