from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# DATABASE_URL is set via environment variable.
# - Local dev (MySQL):     mysql+pymysql://root:password@localhost:3306/course_to_project
# - Production (Supabase): postgresql+psycopg2://postgres:password@db.xxx.supabase.co:5432/postgres
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:1234@localhost:3306/course_to_project"
)

# Auto-add sslmode=require for Supabase/PostgreSQL connections
# (Supabase rejects connections without SSL)
connect_args = {}
engine_kwargs = {
    "pool_pre_ping": True,  # Ping before use to detect stale connections
}

if SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
    connect_args["sslmode"] = "require"
    engine_kwargs.update({
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 1800,  # Recycle every 30min for cloud DB
    })
else:
    # MySQL local dev settings
    engine_kwargs.update({
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 3600,
    })

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


