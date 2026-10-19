"""
Tests run against a throwaway in-memory database, never the real one.
Run from fastapi_backend/:  python -m pytest tests
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import rate_limit
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.employee import Employee
from app.models.user import User
from app.services import storage


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    # Photos and face images kept in the database go to this one too.
    for store in (storage.media_store, storage.face_store):
        if isinstance(store, storage.DatabaseStorage):
            store.sessions = Session
    rate_limit.reset()
    session = Session()
    yield session
    session.close()
    app.dependency_overrides.clear()
    for store in (storage.media_store, storage.face_store):
        if isinstance(store, storage.DatabaseStorage):
            store.sessions = storage.SessionLocal
    engine.dispose()


@pytest.fixture
def client(db):
    return TestClient(app)


def make_org(db, mobile="9000000001", password="org-password", email=None):
    user = User(
        name=f"Org {mobile}",
        mobile_number=mobile,
        email=email or f"{mobile}@example.com",
        password=hash_password(password),
        is_organization=True,
    )
    db.add(user)
    db.commit()
    return user


def make_employee(db, org, mobile="8000000001", member_password="member-pass"):
    user = User(
        name=f"Employee {mobile}",
        mobile_number=mobile,
        email=f"{mobile}@example.com",
        password=hash_password("unused-login-password"),
        is_organization=False,
    )
    db.add(user)
    db.flush()
    db.add(
        Employee(
            user_id=user.org_id,
            first_name="Asha",
            last_name="Rao",
            organisation_id=org.org_id,
            member_password=hash_password(member_password),
        )
    )
    db.commit()
    return user


def auth(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.mobile_number)}"}
