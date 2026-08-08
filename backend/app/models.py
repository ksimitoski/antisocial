import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship, validates
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="user")  # 'user', 'moderator', 'admin'
    is_admin = Column(Boolean, default=False)
    is_system_admin = Column(Boolean, default=False)
    is_confirmed = Column(Boolean, default=False)

    # Security & 2FA / E2EE
    totp_secret = Column(String(100), nullable=True)
    is_totp_enabled = Column(Boolean, default=False)
    totp_backup_codes = Column(Text, nullable=True)
    public_key = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    @validates('username')
    def validate_username(self, key, value):
        if value:
            return value.lower().strip()
        return value


    # Cascading relationships - when user is deleted, all related items are immediately removed
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="author", cascade="all, delete-orphan")
    likes = relationship("Like", back_populates="user", cascade="all, delete-orphan")
    
    requested_friendships = relationship("Friendship", foreign_keys="[Friendship.requester_id]", back_populates="requester", cascade="all, delete-orphan")
    received_friendships = relationship("Friendship", foreign_keys="[Friendship.addressee_id]", back_populates="addressee", cascade="all, delete-orphan")
    
    created_groups = relationship("Group", back_populates="creator", cascade="all, delete-orphan")
    group_memberships = relationship("GroupMember", back_populates="user", cascade="all, delete-orphan")
    email_tokens = relationship("EmailToken", back_populates="user", cascade="all, delete-orphan")
    reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")
    following_relations = relationship("UserFollow", foreign_keys="[UserFollow.follower_id]", back_populates="follower", cascade="all, delete-orphan")
    follower_relations = relationship("UserFollow", foreign_keys="[UserFollow.followed_id]", back_populates="followed", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    security_logs = relationship("SecurityLog", back_populates="user", cascade="all, delete-orphan")



class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    avatar_url = Column(String(255), nullable=True)
    display_name = Column(String(100), nullable=True)

    first_name = Column(String(100), nullable=True)
    first_name_visibility = Column(String(20), default="public")

    last_name = Column(String(100), nullable=True)
    last_name_visibility = Column(String(20), default="public")
    
    bio = Column(Text, nullable=True)
    bio_visibility = Column(String(20), default="public")  # public, private, friends

    location = Column(String(100), nullable=True)
    location_visibility = Column(String(20), default="public")

    birthdate = Column(String(50), nullable=True)
    birthdate_visibility = Column(String(20), default="private")

    phone = Column(String(50), nullable=True)
    phone_visibility = Column(String(20), default="private")

    email_visibility = Column(String(20), default="private")

    dm_privacy = Column(String(20), default="friends")  # options: anyone, friends, none

    # Online status controls: online status choices: 'online', 'offline', 'unknown'
    # visibility setting choices: 'share', 'obscure' (or 'public', 'private', 'friends')
    online_status = Column(String(20), default="online")  # 'online', 'offline', 'unknown'
    online_status_visibility = Column(String(20), default="share")  # 'share', 'obscure'
    last_seen = Column(DateTime, default=datetime.datetime.utcnow, nullable=True)

    # Browser Notification preferences
    notify_messages = Column(Boolean, default=True)
    notify_comments = Column(Boolean, default=True)
    notification_mode = Column(String(20), default="constant")  # 'constant' or 'limited'
    obscure_notification_content = Column(Boolean, default=False)

    # Email Notification preferences (Batch Digest)
    email_notify_messages = Column(Boolean, default=True)
    email_notify_comments = Column(Boolean, default=True)
    email_notify_posts = Column(Boolean, default=True)
    email_notification_frequency = Column(String(20), default="30min")  # 'instant', '30min', 'daily', 'never'
    email_obscure_notification_content = Column(Boolean, default=False)
    last_email_digest_sent = Column(DateTime, nullable=True)

    # User Timezone preference
    timezone = Column(String(50), default="UTC")

    user = relationship("User", back_populates="profile")



class EmailToken(Base):
    __tablename__ = "email_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(100), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="email_tokens")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(100), unique=True, index=True, nullable=False)
    code = Column(String(10), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="reset_tokens")


class Friendship(Base):
    __tablename__ = "friendships"

    id = Column(Integer, primary_key=True, index=True)
    requester_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    addressee_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default="pending")  # pending, accepted
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    requester = relationship("User", foreign_keys=[requester_id], back_populates="requested_friendships")
    addressee = relationship("User", foreign_keys=[addressee_id], back_populates="received_friendships")

    __table_args__ = (
        UniqueConstraint("requester_id", "addressee_id", name="unique_friendship_pair"),
    )


class UserFollow(Base):
    __tablename__ = "user_follows"

    id = Column(Integer, primary_key=True, index=True)
    follower_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    followed_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    follower = relationship("User", foreign_keys=[follower_id], back_populates="following_relations")
    followed = relationship("User", foreign_keys=[followed_id], back_populates="follower_relations")

    __table_args__ = (
        UniqueConstraint("follower_id", "followed_id", name="unique_follower_followed"),
    )


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    creator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_private = Column(Boolean, default=False)
    is_invite_only = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    creator = relationship("User", back_populates="created_groups")
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="group", cascade="all, delete-orphan")
    bans = relationship("GroupBan", back_populates="group", cascade="all, delete-orphan")
    join_requests = relationship("GroupJoinRequest", back_populates="group", cascade="all, delete-orphan")


class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), default="member")  # admin, member
    joined_at = Column(DateTime, default=datetime.datetime.utcnow)

    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="group_memberships")

    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="unique_group_member"),
    )


class GroupBan(Base):
    __tablename__ = "group_bans"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    banned_by_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    group = relationship("Group", back_populates="bans")
    user = relationship("User", foreign_keys=[user_id])
    banned_by = relationship("User", foreign_keys=[banned_by_id])

    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="unique_group_ban"),
    )


class GroupJoinRequest(Base):
    __tablename__ = "group_join_requests"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    group = relationship("Group", back_populates="join_requests")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="unique_group_join_request"),
    )


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=True)
    
    content = Column(Text, nullable=True)
    media_type = Column(String(20), default="none")  # none, image, video
    media_url = Column(String(255), nullable=True)
    
    # Sharing control: public, private, friends, group
    visibility = Column(String(20), default="public")
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    author = relationship("User", back_populates="posts")
    group = relationship("Group", back_populates="posts")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    likes = relationship("Like", back_populates="post", cascade="all, delete-orphan")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    post = relationship("Post", back_populates="comments")
    author = relationship("User", back_populates="comments")


class Like(Base):
    __tablename__ = "likes"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    post = relationship("Post", back_populates="likes")
    user = relationship("User", back_populates="likes")

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="unique_post_like"),
    )


class SiteSetting(Base):
    __tablename__ = "site_settings"

    key = Column(String(50), primary_key=True, index=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class DirectMessage(Base):
    __tablename__ = "direct_messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    is_encrypted = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    sender = relationship("User", foreign_keys=[sender_id])
    recipient = relationship("User", foreign_keys=[recipient_id])


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_token = Column(String(100), unique=True, index=True, nullable=False)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)
    last_active_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="sessions")


class SecurityLog(Base):
    __tablename__ = "security_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    event_type = Column(String(50), nullable=False)  # e.g., 'login', 'login_new_ip', '2fa_enabled', 'password_change'
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="security_logs")


