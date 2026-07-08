from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

# Local dev convenience — loads backend/.env (see .env.example). Render sets
# real env vars directly on the service, so this is a no-op in production.
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bookinguru.db")

is_sqlite = DATABASE_URL.startswith("sqlite")

if is_sqlite:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    # Supabase transaction pooler (port 6543) requires prepared statements disabled
    engine = create_engine(
        DATABASE_URL,
        connect_args={"options": "-c statement_timeout=30000"},
        pool_pre_ping=True,
        pool_recycle=300,
        execution_options={"no_parameters": True},
        # Batch INSERTs *and* UPDATEs into few round-trips. The psycopg2 default
        # ("values_only") batches inserts but sends one round-trip per UPDATE —
        # which made re-syncing ~2,350 daily bookings take minutes over the
        # pooler. "values_plus_batch" uses execute_batch for updates too.
        # Client-side batching → compatible with the pgbouncer transaction pooler.
        executemany_mode="values_plus_batch",
        executemany_batch_page_size=1000,
    )
    # Disable prepared statements for pgbouncer/Supabase pooler compatibility
    @event.listens_for(engine, "connect")
    def connect(dbapi_connection, connection_record):
        dbapi_connection.autocommit = False

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
