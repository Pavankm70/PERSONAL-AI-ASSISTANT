import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Force test environment variables before importing app
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY") or "mock_test_gemini_api_key_valid"

from app.db.session import Base, get_db
from app.main import app
from app.db.models import (
    User, OAuthAccount, Conversation, Message, Document,
    DocumentChunk, Timetable, TimetablePeriod, TimetableEntry, AcademicEvent, Plan, PlanTask,
    IntegrationConnection, ToolExecutionLog
)
from app.core.security import create_access_token

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def test_user(db_session):
    user = User(
        id="usr_test_101",
        email="test.user@university.edu",
        full_name="Test Student",
        timezone="America/Los_Angeles",
        onboarding_complete=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.fixture(scope="function")
def auth_headers(test_user):
    token = create_access_token({"sub": test_user.id, "email": test_user.email})
    return {"Authorization": f"Bearer {token}"}
