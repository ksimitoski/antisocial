import os
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/antisocial.db")

# Ensure directory for sqlite file exists if using sqlite
if DATABASE_URL.startswith("sqlite"):
    db_path = DATABASE_URL.replace("sqlite:///", "")
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

# Enable foreign key enforcement for SQLite
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def run_db_migrations(engine_obj):
    """Automatically alter SQLite tables to add missing columns without losing existing data."""
    try:
        inspector = inspect(engine_obj)
        if "user_profiles" in inspector.get_table_names():
            columns = [c["name"] for c in inspector.get_columns("user_profiles")]
            with engine_obj.begin() as conn:
                if "display_name" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN display_name VARCHAR(100)"))
                if "first_name" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN first_name VARCHAR(100)"))
                if "first_name_visibility" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN first_name_visibility VARCHAR(20) DEFAULT 'public'"))
                if "last_name" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN last_name VARCHAR(100)"))
                if "last_name_visibility" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN last_name_visibility VARCHAR(20) DEFAULT 'public'"))
                if "dm_privacy" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN dm_privacy VARCHAR(20) DEFAULT 'friends'"))
                if "email_visibility" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN email_visibility VARCHAR(20) DEFAULT 'private'"))
                if "online_status" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN online_status VARCHAR(20) DEFAULT 'online'"))
                if "online_status_visibility" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN online_status_visibility VARCHAR(20) DEFAULT 'share'"))
                if "last_seen" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN last_seen DATETIME"))
                if "notify_messages" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN notify_messages BOOLEAN DEFAULT 1"))
                if "notify_comments" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN notify_comments BOOLEAN DEFAULT 1"))
                if "notification_mode" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN notification_mode VARCHAR(20) DEFAULT 'constant'"))
                if "obscure_notification_content" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN obscure_notification_content BOOLEAN DEFAULT 0"))
                if "email_notify_messages" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN email_notify_messages BOOLEAN DEFAULT 1"))
                if "email_notify_comments" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN email_notify_comments BOOLEAN DEFAULT 1"))
                if "email_notify_posts" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN email_notify_posts BOOLEAN DEFAULT 1"))
                if "email_notification_frequency" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN email_notification_frequency VARCHAR(20) DEFAULT '30min'"))
                if "email_obscure_notification_content" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN email_obscure_notification_content BOOLEAN DEFAULT 0"))
                if "last_email_digest_sent" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN last_email_digest_sent DATETIME"))
                if "timezone" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC'"))
                if "public_key" not in columns:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN public_key TEXT"))

        if "users" in inspector.get_table_names():
            user_columns = [c["name"] for c in inspector.get_columns("users")]
            with engine_obj.begin() as conn:
                if "role" not in user_columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user'"))
                if "totp_secret" not in user_columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN totp_secret VARCHAR(100)"))
                if "is_totp_enabled" not in user_columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN is_totp_enabled BOOLEAN DEFAULT 0"))
                if "totp_backup_codes" not in user_columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN totp_backup_codes TEXT"))
                if "public_key" not in user_columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN public_key TEXT"))
                conn.execute(text("UPDATE users SET username = LOWER(username) WHERE username != LOWER(username)"))

        if "posts" in inspector.get_table_names():
            post_columns = [c["name"] for c in inspector.get_columns("posts")]
            with engine_obj.begin() as conn:
                if "expires_at" not in post_columns:
                    conn.execute(text("ALTER TABLE posts ADD COLUMN expires_at DATETIME"))

        if "direct_messages" in inspector.get_table_names():
            dm_columns = [c["name"] for c in inspector.get_columns("direct_messages")]
            with engine_obj.begin() as conn:
                if "expires_at" not in dm_columns:
                    conn.execute(text("ALTER TABLE direct_messages ADD COLUMN expires_at DATETIME"))
                if "is_encrypted" not in dm_columns:
                    conn.execute(text("ALTER TABLE direct_messages ADD COLUMN is_encrypted BOOLEAN DEFAULT 0"))

        if "groups" in inspector.get_table_names():
            group_columns = [c["name"] for c in inspector.get_columns("groups")]
            with engine_obj.begin() as conn:
                if "is_private" not in group_columns:
                    conn.execute(text("ALTER TABLE groups ADD COLUMN is_private BOOLEAN DEFAULT 0"))
                if "is_invite_only" not in group_columns:
                    conn.execute(text("ALTER TABLE groups ADD COLUMN is_invite_only BOOLEAN DEFAULT 0"))

        if "comments" in inspector.get_table_names():
            comment_columns = [c["name"] for c in inspector.get_columns("comments")]
            with engine_obj.begin() as conn:
                if "parent_id" not in comment_columns:
                    conn.execute(text("ALTER TABLE comments ADD COLUMN parent_id INTEGER REFERENCES comments(id) ON DELETE CASCADE"))

    except Exception as e:
        print(f"Database migration notice: {e}", flush=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

