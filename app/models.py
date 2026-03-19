"""SQLAlchemy models for multi-user Personal Assistant service."""

import os
from sqlalchemy import Column, Integer, String, JSON, create_engine, UniqueConstraint
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
    notify_email      = Column(String, nullable=True)   # email address to send daily schedule to
    gmail_query       = Column(String, nullable=True)   # custom Gmail search query (deprecated: now fetch all)
    email_sync_hours  = Column(Integer, default=24)     # hours to look back when fetching emails
    sender_priorities = Column(JSON, default={})        # {"sender@example.com": "high"|"medium"|"low"}
    last_schedule_sent = Column(String, nullable=True) # YYYY-MM-DD of last schedule send
    last_email_sync_at = Column(String, nullable=True) # ISO timestamp of last email sync

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


class SenderPriority(Base):
    """Maps a user to a specific sender and priority."""

    __tablename__ = "sender_priorities"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    user_id  = Column(String, nullable=False)    # References users.id
    sender   = Column(String, nullable=False)
    priority = Column(String, default="medium")  # "high", "medium", "low"

    def __repr__(self) -> str:
        return f"<SenderPriority user_id={self.user_id!r} sender={self.sender!r} priority={self.priority!r}>"


class SeenEmail(Base):
    """Tracks already-processed Gmail message IDs per account."""

    __tablename__ = "seen_emails"
    __table_args__ = (
        UniqueConstraint("account_id", "message_id", name="uq_seen_emails_account_message"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String, nullable=False, index=True)
    message_id = Column(String, nullable=False)

    def __repr__(self) -> str:
        return f"<SeenEmail account_id={self.account_id!r} message_id={self.message_id!r}>"


# SQLite database stored in data/ at the project root
# _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# _DATA_DIR = os.path.join(_BASE_DIR, "data")
# os.makedirs(_DATA_DIR, exist_ok=True)

database_url = (os.getenv("DATABASE_URL") or "").strip().strip('"').strip("'")

# Render commonly provides postgres://... while SQLAlchemy expects postgresql://...
if database_url.startswith("postgres://"):
    database_url = "postgresql://" + database_url[len("postgres://") :]

if not database_url or not (
    database_url.startswith("postgresql://")
    or database_url.startswith("postgresql+")
):
    raise ValueError(
        "DATABASE_URL must be a PostgreSQL URL (postgresql://...). "
        "Please configure it in your environment."
    )

engine = create_engine(
    database_url
)
Base.metadata.create_all(engine)

# Lightweight migration: add columns/tables if upgrading from an older schema
from sqlalchemy import inspect, text as _text

inspector = inspect(engine)
if "last_schedule_sent" not in [c["name"] for c in inspector.get_columns("users")]:
    print("Adding last_schedule_sent column to users table")
    with engine.connect() as conn:
        conn.execute(_text('ALTER TABLE users ADD COLUMN last_schedule_sent VARCHAR'))
        conn.commit()

if "last_email_sync_at" not in [c["name"] for c in inspector.get_columns("users")]:
    print("Adding last_email_sync_at column to users table")
    with engine.connect() as conn:
        conn.execute(_text('ALTER TABLE users ADD COLUMN last_email_sync_at VARCHAR'))
        conn.commit()

#     _cols = [c["name"] for c in inspect(engine).get_columns("users")]
#     if "gmail_query" not in _cols:
#         _conn.execute(_text("ALTER TABLE users ADD COLUMN gmail_query VARCHAR"))
#         _conn.commit()
#     if "email_sync_hours" not in _cols:
#         _conn.execute(_text("ALTER TABLE users ADD COLUMN email_sync_hours INTEGER DEFAULT 24"))
#         _conn.commit()
#     if "sender_priorities" not in _cols:
#         _conn.execute(_text("ALTER TABLE users ADD COLUMN sender_priorities JSON DEFAULT '{}'"))
#         _conn.commit()

#     # Create the sender_priorities table if it doesn't exist
#     if not inspect(engine).has_table("sender_priorities"):
#         SenderPriority.__table__.create(engine)

Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def get_db():
    """FastAPI dependency for database sessions."""
    db = Session()
    try:
        yield db
    finally:
        db.close()

# Perform data migration from users.sender_priorities JSON to sender_priorities table
# This runs once on startup and safely converts legacy data into the new table.
import json
db = Session()
try:
    users_with_json = db.execute(
        _text(
            """
            SELECT id, sender_priorities
            FROM users
            WHERE sender_priorities IS NOT NULL
              AND CAST(sender_priorities AS TEXT) <> '{}' 
            """
        )
    ).mappings().all()
    if users_with_json:
        for user_row in users_with_json:
            user_id = user_row["id"]
            priorities_json = user_row["sender_priorities"]
            
            # Determine if it is a string or already parsed JSON 
            if isinstance(priorities_json, str):
                try:
                    priorities = json.loads(priorities_json)
                except json.JSONDecodeError:
                    continue
            else:
                priorities = priorities_json
                
            if isinstance(priorities, dict) and priorities:
                for sender, priority in priorities.items():
                    # Check if priority already migrated
                    exists = db.query(SenderPriority).filter(
                        SenderPriority.user_id == user_id,
                        SenderPriority.sender == sender
                    ).first()
                    
                    if not exists:
                        new_record = SenderPriority(user_id=user_id, sender=sender, priority=priority)
                        db.add(new_record)
                
                # Clear out the JSON to avoid re-migrating
                db.execute(_text("UPDATE users SET sender_priorities = '{}' WHERE id = :uid"), {"uid": user_id})
        
        db.commit()
except Exception as e:
    import logging
    logging.getLogger(__name__).error(f"Failed to migrate sender priorities: {e}")
finally:
    db.close()
