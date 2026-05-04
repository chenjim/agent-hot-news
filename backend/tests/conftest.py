import os

# Must set before any app imports so settings use test values
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

import asyncio
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    # Replace VectorType with JSON for SQLite test compatibility
    @event.listens_for(Base.metadata, "before_create")
    def _replace_vector_type(target, connection, **kw):
        for table in target.tables.values():
            for col in list(table.columns):
                if hasattr(col.type, 'dim'):  # VectorType
                    from sqlalchemy import JSON
                    col.type = JSON()

    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db(engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    connection = engine.connect()
    transaction = connection.begin_nested()
    session = SessionLocal(bind=connection)

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if connection.in_nested_transaction():
            connection.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    from fastapi import FastAPI
    from app.api.v1.api import api_router

    test_app = FastAPI()
    test_app.include_router(api_router, prefix="/api/v1")

    @test_app.get("/health")
    def health_check():
        return {"status": "ok"}

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db

    with TestClient(test_app) as c:
        yield c

    test_app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()
