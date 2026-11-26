"""Engine and session factory (PostgreSQL or SQLite)."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
    future=True,
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()
        dbapi_conn.isolation_level = None  # we emit BEGIN ourselves (see below)

    @event.listens_for(engine, "begin")
    def _sqlite_begin_immediate(conn):
        # Take the write lock up front: avoids SQLITE_BUSY_SNAPSHOT when a read transaction
        # later tries to write while another connection committed (concurrent claims).
        conn.exec_driver_sql("BEGIN IMMEDIATE")


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

# Read-only requests (HTTP GET) use a second engine with *deferred* transactions. Under WAL a reader never
# blocks the writer, so a slow or aborted GET response can no longer hold SQLite's write lock for seconds
# (which made the scheduler tick and every other write wait, then fail with "database is locked").
if _is_sqlite:
    read_engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30}, future=True)

    @event.listens_for(read_engine, "connect")
    def _sqlite_read_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    SessionRead = sessionmaker(bind=read_engine, autoflush=False, expire_on_commit=False, future=True)
else:
    SessionRead = SessionLocal
IS_SQLITE = _is_sqlite
