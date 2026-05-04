from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from app.core.config import get_settings
from loguru import logger

settings = get_settings()

_connect_args = {}
_engine_kwargs = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
else:
    _engine_kwargs = {"pool_size": 5, "max_overflow": 10}

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG,
    connect_args=_connect_args,
    **_engine_kwargs,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def _register_pgvector(dbapi_connection, connection_record):
    """Register pgvector extension on PostgreSQL connections."""
    try:
        dbapi_connection.cursor().execute("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception:
        pass  # not PostgreSQL or extension unavailable


if settings.DATABASE_URL.startswith("postgresql"):
    event.listen(engine, "connect", _register_pgvector)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
