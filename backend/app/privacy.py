import datetime
from sqlalchemy.orm import Session
from app import models

def is_friends(db: Session, user1_id: int, user2_id: int) -> bool:
    """Check if two users are accepted friends."""
    if not user1_id or not user2_id or user1_id == user2_id:
        return True if user1_id == user2_id else False

    friendship = db.query(models.Friendship).filter(
        models.Friendship.status == "accepted",
        (
            (models.Friendship.requester_id == user1_id) & (models.Friendship.addressee_id == user2_id)
        ) | (
            (models.Friendship.requester_id == user2_id) & (models.Friendship.addressee_id == user1_id)
        )
    ).first()
    return friendship is not None


def is_group_banned(db: Session, group_id: int, user_id: int) -> bool:
    """Check if a user is banned from a group."""
    if not group_id or not user_id:
        return False
    ban = db.query(models.GroupBan).filter(
        models.GroupBan.group_id == group_id,
        models.GroupBan.user_id == user_id
    ).first()
    return ban is not None


def is_group_admin(db: Session, group_id: int, user_id: int) -> bool:
    """Check if a user is creator or admin of a group."""
    if not group_id or not user_id:
        return False
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if group and group.creator_id == user_id:
        return True
    member = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id,
        models.GroupMember.user_id == user_id,
        models.GroupMember.role == "admin"
    ).first()
    return member is not None


def is_group_member(db: Session, group_id: int, user_id: int) -> bool:
    """Check if a user is an active, unbanned member of a group."""
    if not group_id or not user_id:
        return False

    if is_group_banned(db, group_id, user_id):
        return False

    membership = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id,
        models.GroupMember.user_id == user_id
    ).first()
    return membership is not None


def can_view_field(db: Session, viewer_id: int | None, target_user_id: int, visibility_setting: str) -> bool:
    """
    Check if viewer_id can see a profile field of target_user_id.
    Note: Admin status does NOT bypass privacy controls!
    """
    if viewer_id == target_user_id:
        return True

    if visibility_setting == "public":
        return True

    if visibility_setting == "private":
        return False

    if visibility_setting == "friends":
        if not viewer_id:
            return False
        return is_friends(db, viewer_id, target_user_id)

    return False


def is_admin_or_moderator(db: Session, user_id: int | None) -> bool:
    """Check if a user is a System Admin or Moderator."""
    if not user_id:
        return False
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return False
    return bool(user.is_admin or (user.role in ["admin", "moderator"]))


def can_view_post(db: Session, viewer_id: int | None, post: models.Post) -> bool:
    """
    Check if viewer_id can view a specific post.
    Admins and Moderators have access to all group posts even if not joined to that group.
    """
    if post.group_id is not None:
        if not viewer_id:
            return False
        if not is_group_member(db, post.group_id, viewer_id) and not is_admin_or_moderator(db, viewer_id):
            return False

    if viewer_id == post.author_id:
        return True

    if post.visibility == "public":
        return True

    if post.visibility in ["internal-only", "internal"]:
        if not viewer_id:
            return False
        return True

    if post.visibility == "private":
        return False

    if post.visibility == "friends":
        if not viewer_id:
            return False
        return is_friends(db, viewer_id, post.author_id)

    if post.visibility == "group":
        if not viewer_id or not post.group_id:
            return False
        return is_group_member(db, post.group_id, viewer_id) or is_admin_or_moderator(db, viewer_id)

    return False


def get_display_name(user: models.User) -> str:
    """Returns display_name if set, otherwise username."""
    if user and user.profile and user.profile.display_name and user.profile.display_name.strip():
        return user.profile.display_name.strip()
    return user.username if user else "Unknown"


def get_online_status(db: Session, viewer_id: int | None, target_user: models.User) -> str:
    """
    Returns 'online', 'offline', or 'unknown'.
    If target_user chooses to obscure their online status (or visibility is set to 'obscure'/'private'/'friends' when unauthorized),
    returns 'unknown'. Owners always see their own raw status setting.
    """
    profile = target_user.profile
    if not profile:
        return "unknown"

    status_val = (profile.online_status or "online").lower()
    vis_val = (profile.online_status_visibility or "share").lower()

    # Calculate real activity status: if user set status to 'online', check if last_seen is within the last 5 minutes (300 seconds)
    effective_status = status_val
    if status_val == "online":
        if not profile.last_seen:
            effective_status = "offline"
        else:
            diff_seconds = (datetime.datetime.utcnow() - profile.last_seen).total_seconds()
            if diff_seconds > 300:  # Inactive for over 5 minutes
                effective_status = "offline"

    if viewer_id == target_user.id:
        return effective_status

    # Explicit choice: 'obscure' forces status to display as 'unknown' to others
    if vis_val == "obscure" or vis_val == "private":
        return "unknown"

    if vis_val == "share" or vis_val == "public":
        return effective_status

    if vis_val == "friends":
        if viewer_id and is_friends(db, viewer_id, target_user.id):
            return effective_status
        return "unknown"

    return "unknown"


def filter_profile_for_viewer(db: Session, viewer_id: int | None, target_user: models.User) -> dict:
    """
    Returns a dict of profile information filtered strictly by privacy settings.
    If target_user has no profile or fields are hidden, return None or filtered text.
    """
    profile = target_user.profile
    is_owner = (viewer_id == target_user.id)

    if not profile:
        return {
            "username": target_user.username,
            "display_name": target_user.username,
            "avatar_url": None,
            "first_name": None,
            "last_name": None,
            "bio": None,
            "location": None,
            "birthdate": None,
            "phone": None,
            "email": target_user.email if is_owner else None,
            "email_visibility": "private" if is_owner else None,
            "online_status": "unknown",
            "online_status_visibility": "obscure" if is_owner else None,
        }

    email_vis = getattr(profile, "email_visibility", "private") or "private"
    online_vis = getattr(profile, "online_status_visibility", "obscure") or "obscure"

    return {
        "username": target_user.username,
        "display_name": profile.display_name if profile.display_name else target_user.username,
        "avatar_url": profile.avatar_url,

        "first_name": profile.first_name if is_owner or can_view_field(db, viewer_id, target_user.id, profile.first_name_visibility) else None,
        "first_name_visibility": profile.first_name_visibility if is_owner else None,

        "last_name": profile.last_name if is_owner or can_view_field(db, viewer_id, target_user.id, profile.last_name_visibility) else None,
        "last_name_visibility": profile.last_name_visibility if is_owner else None,

        "bio": profile.bio if is_owner or can_view_field(db, viewer_id, target_user.id, profile.bio_visibility) else None,
        "bio_visibility": profile.bio_visibility if is_owner else None,

        "location": profile.location if is_owner or can_view_field(db, viewer_id, target_user.id, profile.location_visibility) else None,
        "location_visibility": profile.location_visibility if is_owner else None,

        "birthdate": profile.birthdate if is_owner or can_view_field(db, viewer_id, target_user.id, profile.birthdate_visibility) else None,
        "birthdate_visibility": profile.birthdate_visibility if is_owner else None,

        "phone": profile.phone if is_owner or can_view_field(db, viewer_id, target_user.id, profile.phone_visibility) else None,
        "phone_visibility": profile.phone_visibility if is_owner else None,

        "email": target_user.email if is_owner or can_view_field(db, viewer_id, target_user.id, email_vis) else None,
        "email_visibility": email_vis if is_owner else None,

        "dm_privacy": profile.dm_privacy or "friends",

        "online_status": get_online_status(db, viewer_id, target_user),
        "online_status_visibility": online_vis if is_owner else None,

        "notify_messages": getattr(profile, "notify_messages", True) if is_owner else None,
        "notify_comments": getattr(profile, "notify_comments", True) if is_owner else None,
        "notification_mode": getattr(profile, "notification_mode", "constant") if is_owner else None,
        "obscure_notification_content": getattr(profile, "obscure_notification_content", False) if is_owner else None,
        "email_notify_messages": getattr(profile, "email_notify_messages", True) if is_owner else None,
        "email_notify_comments": getattr(profile, "email_notify_comments", True) if is_owner else None,
        "email_notify_posts": getattr(profile, "email_notify_posts", True) if is_owner else None,
        "email_notification_frequency": getattr(profile, "email_notification_frequency", "30min") if is_owner else None,
        "email_obscure_notification_content": getattr(profile, "email_obscure_notification_content", False) if is_owner else None,
        "timezone": getattr(profile, "timezone", "UTC") if is_owner else None,
    }

