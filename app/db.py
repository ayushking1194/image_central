from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def ensure_sqlite_columns():
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as connection:
        result = connection.execute(text("PRAGMA table_info(prism_centrals)"))
        columns = {row[1] for row in result}
        if "connected" not in columns:
            connection.execute(text("ALTER TABLE prism_centrals ADD COLUMN connected BOOLEAN"))
        if "last_checked_at" not in columns:
            connection.execute(
                text("ALTER TABLE prism_centrals ADD COLUMN last_checked_at DATETIME")
            )
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()