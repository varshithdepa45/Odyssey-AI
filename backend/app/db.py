import json
from datetime import datetime, timezone

from sqlalchemy import Text, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator, UserDefinedType

from .config import get_settings

settings = get_settings()

if settings.is_postgres:
    # prepare_threshold=None keeps psycopg compatible with Supabase's transaction pooler.
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"prepare_threshold": None},
    )
else:
    engine = create_engine(settings.sqlalchemy_url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def _configure_sqlite(connection, _record):
        connection.isolation_level = None  # SQLAlchemy issues BEGIN itself, below
        connection.execute("PRAGMA foreign_keys=ON")

    @event.listens_for(engine, "begin")
    def _begin_immediate(connection):
        # Take the write lock up front so concurrent requests queue instead of racing. This is what
        # SELECT ... FOR UPDATE does on Postgres; SQLite ignores that clause.
        connection.exec_driver_sql("BEGIN IMMEDIATE")

SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class _PGVector(UserDefinedType):
    cache_ok = True

    def __init__(self, dim: int):
        self.dim = dim

    def get_col_spec(self, **kw):
        return f"vector({self.dim})"


class Embedding(TypeDecorator):
    """pgvector column on Postgres, JSON text elsewhere (SQLite for dev and tests)."""

    impl = Text
    cache_ok = True

    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PGVector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        return None if value is None else vector_literal(value)

    def process_result_value(self, value, dialect):
        return json.loads(value) if isinstance(value, str) else value


def vector_literal(values) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def utcnow() -> datetime:
    """Naive UTC, so values compare the same on SQLite and Postgres."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (registers tables)
    from .migrations import migrate

    if settings.is_postgres:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    migrate(engine)
    if settings.is_postgres:
        # Supabase publishes every public table through its REST API. Row level security
        # with no policies locks that door; this backend connects as the table owner,
        # which bypasses RLS.
        with engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                conn.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS doc_chunks_embedding_idx "
                "ON doc_chunks USING hnsw (embedding vector_cosine_ops)"
            ))
