"""SQLAlchemy models for multi-user Personal Assistant service."""

import json
from sqlalchemy import Column, String, JSON, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class User(Base):
    """Represents a signed-up user with their Google OAuth token and preferences."""

    __tablename__ = "users"

    id           = Column(String, primary_key=True)   # Google user ID
    email        = Column(String, unique=True, nullable=False)
    token_json   = Column(JSON, nullable=False)        # OAuth2 credentials as dict
    notify_time  = Column(String, default="07:00")  # "HH:MM" 24-hour format
    timezone     = Column(String, default="UTC")    # e.g. "Asia/Kolkata"
    notify_email = Column(String, nullable=True)    # email address to send daily schedule to

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


# SQLite database stored next to this file
engine = create_engine(
    "sqlite:///users.db",
    connect_args={"check_same_thread": False},  # needed for multi-threaded FastAPI
)
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
