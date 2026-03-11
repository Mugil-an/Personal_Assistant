"""SQLAlchemy models for multi-user Personal Assistant service."""

import os
from sqlalchemy import Column, String, JSON, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class User(Base):
    """Represents a signed-up user with their Google OAuth token and preferences."""

    __tablename__ = "users"

    id           = Column(String, primary_key=True)   # Google user ID
    email        = Column(String, unique=True, nullable=False)
    token_json   = Column(JSON, nullable=False)        # OAuth2 credentials as dict
    notify_time  = Column(String, default="07:00")     # "HH:MM" 24-hour format
    timezone     = Column(String, default="UTC")       # e.g. "Asia/Kolkata"
    notify_email = Column(String, nullable=True)       # email address to send daily schedule to
    gmail_query  = Column(String, nullable=True)       # custom Gmail search query

    def __repr__(self) -> str:
        return f"<User id={self.id!r} email={self.email!r} notify_time={self.notify_time!r}>"


class LinkedAccount(Base):
    """A secondary Gmail account linked to a primary user."""

    __tablename__ = "linked_accounts"

    id         = Column(String, primary_key=True)  # Google user ID of the linked account
    owner_id   = Column(String, nullable=False)    # Primary user's ID (references users.id)
    email      = Column(String, nullable=False)
    token_json = Column(JSON, nullable=False)

    def __repr__(self) -> str:
        return f"<LinkedAccount id={self.id!r} email={self.email!r} owner={self.owner_id!r}>"


# SQLite database stored in data/ at the project root
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
os.makedirs(_DATA_DIR, exist_ok=True)

engine = create_engine(
    f"sqlite:///{os.path.join(_DATA_DIR, 'users.db')}",
    connect_args={"check_same_thread": False},  # needed for multi-threaded FastAPI
)
Base.metadata.create_all(engine)

# Lightweight migration: add gmail_query column if upgrading from an older schema
from sqlalchemy import inspect, text as _text
with engine.connect() as _conn:
    _cols = [c["name"] for c in inspect(engine).get_columns("users")]
    if "gmail_query" not in _cols:
        _conn.execute(_text("ALTER TABLE users ADD COLUMN gmail_query VARCHAR"))
        _conn.commit()

Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
