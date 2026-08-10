import datetime
import re
from pydantic import BaseModel, EmailStr, ConfigDict, field_validator
from typing import Optional, List

class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str
    password_confirm: Optional[str] = None
    captcha_id: Optional[str] = None
    captcha_answer: Optional[str] = None

    @field_validator('username')
    @classmethod
    def validate_and_lowercase_username(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Username is required")
        v = v.strip().lower()
        if len(v) > 40:
            raise ValueError("Username must be at most 40 characters long")
        if not re.match(r'^[a-z][a-z0-9_]*$', v):
            raise ValueError("Username must start with a letter and contain only alphanumeric characters and underscores")
        return v

class UserLogin(BaseModel):
    username_or_email: str
    password: str
    totp_code: Optional[str] = None
    remember_me: Optional[bool] = False

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetVerifyCode(BaseModel):
    email: EmailStr
    code: str

class PasswordResetConfirm(BaseModel):
    token: Optional[str] = None
    email: Optional[EmailStr] = None
    code: Optional[str] = None
    password: str
    password_confirm: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: str = "user"
    is_admin: bool
    is_confirmed: bool
    is_totp_enabled: bool = False


class TOTPVerifyRequest(BaseModel):
    code: str

class PublicKeyUpdate(BaseModel):
    public_key: str


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    first_name_visibility: Optional[str] = None
    last_name: Optional[str] = None
    last_name_visibility: Optional[str] = None
    bio: Optional[str] = None
    bio_visibility: Optional[str] = None
    location: Optional[str] = None
    location_visibility: Optional[str] = None
    birthdate: Optional[str] = None
    birthdate_visibility: Optional[str] = None
    phone: Optional[str] = None
    phone_visibility: Optional[str] = None
    email: Optional[EmailStr] = None
    email_visibility: Optional[str] = None
    avatar_url: Optional[str] = None
    dm_privacy: Optional[str] = None
    online_status: Optional[str] = None
    online_status_visibility: Optional[str] = None
    notify_messages: Optional[bool] = None
    notify_comments: Optional[bool] = None
    notification_mode: Optional[str] = None
    obscure_notification_content: Optional[bool] = None
    email_notify_messages: Optional[bool] = None
    email_notify_comments: Optional[bool] = None
    email_notify_posts: Optional[bool] = None
    email_notification_frequency: Optional[str] = None
    email_obscure_notification_content: Optional[bool] = None
    timezone: Optional[str] = None
    public_key: Optional[str] = None


class DirectMessageCreate(BaseModel):
    recipient_username: str
    content: str
    is_encrypted: Optional[bool] = False
    expires_in: Optional[str] = None  # '1h', '24h', '7d', 'none'


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: Optional[str] = None
    is_admin: bool
    is_confirmed: bool
    is_totp_enabled: bool = False
    public_key: Optional[str] = None
    created_at: datetime.datetime

class PostCreate(BaseModel):
    content: Optional[str] = None
    visibility: str = "public"  # public, private, friends, group
    group_id: Optional[int] = None
    expires_in: Optional[str] = None

class PostUpdate(BaseModel):
    content: Optional[str] = None
    visibility: Optional[str] = None

class CommentCreate(BaseModel):
    content: str
    parent_id: Optional[int] = None

class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_private: bool = False

class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_private: Optional[bool] = None

class GroupInvite(BaseModel):
    username: str

class AdminUserUpdate(BaseModel):
    is_confirmed: Optional[bool] = None
    is_admin: Optional[bool] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class RoleUpdate(BaseModel):
    role: str  # 'user', 'moderator', 'admin'

class SiteSettingUpdate(BaseModel):
    banner_text: Optional[str] = None
    page_text: Optional[str] = None
    accent_color: Optional[str] = None
    site_domain: Optional[str] = None


class PostPrivacyUpdate(BaseModel):
    visibility: str

class UserDelete(BaseModel):
    password: Optional[str] = None

