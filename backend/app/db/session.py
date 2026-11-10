from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Handle sqlite check_same_thread
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

from sqlalchemy import event

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    # Import all models to register them on Base.metadata
    import app.db.models
    Base.metadata.create_all(bind=engine)

    # Safe migration: ensure capabilities column exists in integration_connections
    from sqlalchemy import text
    with engine.connect() as conn:
        try:
            res = conn.execute(text("PRAGMA table_info(integration_connections)"))
            cols = [row[1] for row in res.fetchall()]
            if "capabilities" not in cols and len(cols) > 0:
                conn.execute(text("ALTER TABLE integration_connections ADD COLUMN capabilities JSON DEFAULT '{}'"))
                conn.commit()
        except Exception:
            pass

        # Safe migration: ensure new plan columns exist in plans
        try:
            res = conn.execute(text("PRAGMA table_info(plans)"))
            cols = [row[1] for row in res.fetchall()]
            if cols:
                plan_cols = [
                    ("subject", "VARCHAR(255)"),
                    ("learning_goal", "TEXT"),
                    ("start_date", "VARCHAR(10)"),
                    ("end_date", "VARCHAR(10)"),
                    ("duration_days", "INTEGER"),
                    ("daily_hours_target", "FLOAT DEFAULT 2.0"),
                    ("preferred_study_days", "JSON DEFAULT '[]'"),
                    ("generation_status", "VARCHAR(30) DEFAULT 'complete'"),
                ]
                for col_name, col_type in plan_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE plans ADD COLUMN {col_name} {col_type}"))
                conn.commit()
        except Exception:
            pass

        # Safe migration: ensure new task scheduling & hierarchy columns exist in plan_tasks
        try:
            res = conn.execute(text("PRAGMA table_info(plan_tasks)"))
            cols = [row[1] for row in res.fetchall()]
            if cols:
                task_cols = [
                    ("scheduled_date", "VARCHAR(10)"),
                    ("start_time", "VARCHAR(30)"),
                    ("end_time", "VARCHAR(30)"),
                    ("timezone", "VARCHAR(64)"),
                    ("google_calendar_event_id", "VARCHAR(255)"),
                    ("month_number", "INTEGER"),
                    ("week_number", "INTEGER"),
                    ("day_number", "INTEGER"),
                    ("task_order", "INTEGER DEFAULT 0"),
                    ("task_type", "VARCHAR(30) DEFAULT 'daily'"),
                    ("day_label", "VARCHAR(30)"),
                    ("week_label", "VARCHAR(30)"),
                    ("month_label", "VARCHAR(30)"),
                    ("milestone_group", "VARCHAR(255)"),
                    ("created_at", "DATETIME"),
                    ("updated_at", "DATETIME"),
                ]
                for col_name, col_type in task_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE plan_tasks ADD COLUMN {col_name} {col_type}"))
                conn.commit()
        except Exception:
            pass

        # Safe migration: ensure new structured document columns exist in documents
        try:
            res = conn.execute(text("PRAGMA table_info(documents)"))
            cols = [row[1] for row in res.fetchall()]
            if cols:
                doc_cols = [
                    ("document_type", "VARCHAR(50) DEFAULT 'NOTES'"),
                    ("file_path", "VARCHAR(512)"),
                    ("processing_status", "VARCHAR(30) DEFAULT 'UPLOADED'"),
                    ("processing_error", "TEXT"),
                    ("processed_at", "DATETIME"),
                    ("document_version", "INTEGER DEFAULT 1"),
                    ("is_active", "BOOLEAN DEFAULT 1"),
                    ("extracted_data", "JSON"),
                ]
                for col_name, col_type in doc_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE documents ADD COLUMN {col_name} {col_type}"))
                conn.commit()
        except Exception:
            pass

        # Safe migration: ensure new timetable columns exist in timetable_entries
        try:
            res = conn.execute(text("PRAGMA table_info(timetable_entries)"))
            cols = [row[1] for row in res.fetchall()]
            if cols:
                tt_cols = [
                    ("document_id", "VARCHAR(36)"),
                    ("class_type", "VARCHAR(50)"),
                    ("academic_year", "VARCHAR(50)"),
                    ("semester", "VARCHAR(50)"),
                    ("source_page", "INTEGER DEFAULT 1"),
                    ("source_row", "INTEGER"),
                    ("confidence", "FLOAT DEFAULT 1.0"),
                    ("additional_details", "JSON"),
                    ("updated_at", "DATETIME"),
                ]
                for col_name, col_type in tt_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE timetable_entries ADD COLUMN {col_name} {col_type}"))
                conn.commit()
        except Exception:
            pass

        # Safe migration: ensure timetables and timetable_periods tables and columns exist
        try:
            res = conn.execute(text("PRAGMA table_info(timetables)"))
            cols = [row[1] for row in res.fetchall()]
            if cols:
                t_cols = [
                    ("name", "VARCHAR(255) DEFAULT 'My Timetable'"),
                    ("academic_year", "VARCHAR(50)"),
                    ("semester", "VARCHAR(50)"),
                    ("section", "VARCHAR(50)"),
                    ("updated_at", "DATETIME"),
                ]
                for col_name, col_type in t_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE timetables ADD COLUMN {col_name} {col_type}"))
                conn.commit()
        except Exception:
            pass

        try:
            res = conn.execute(text("PRAGMA table_info(timetable_periods)"))
            cols = [row[1] for row in res.fetchall()]
            if cols:
                p_cols = [
                    ("period_number", "INTEGER"),
                    ("subject_code", "VARCHAR(50)"),
                    ("room", "VARCHAR(100)"),
                    ("faculty", "VARCHAR(255)"),
                    ("class_type", "VARCHAR(50) DEFAULT 'Theory'"),
                    ("notes", "TEXT"),
                    ("updated_at", "DATETIME"),
                ]
                for col_name, col_type in p_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE timetable_periods ADD COLUMN {col_name} {col_type}"))
                conn.commit()
        except Exception:
            pass
