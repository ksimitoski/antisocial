from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query

from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app import models, schemas, auth, privacy

router = APIRouter(prefix="/api/users", tags=["Users"])

@router.get("/online-statuses")
def get_online_statuses(
    usernames: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional)
):
    viewer_id = current_user.id if current_user else None
    query = db.query(models.User)
    if usernames:
        u_list = [u.strip() for u in usernames.split(",") if u.strip()]
        if u_list:
            query = query.filter(models.User.username.in_(u_list))
    
    users = query.all()
    statuses = {}
    for u in users:
        statuses[u.username] = privacy.get_online_status(db, viewer_id, u)
    
    return {"statuses": statuses}

@router.get("/profile/{username}")
def get_user_profile(
    username: str,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional)
):
    target_user = db.query(models.User).filter(models.User.username == username.strip().lower()).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    viewer_id = current_user.id if current_user else None
    filtered_profile = privacy.filter_profile_for_viewer(db, viewer_id, target_user)
    
    # Also attach friendship status if viewer is logged in
    friend_status = None
    is_following = False
    if current_user and current_user.id != target_user.id:
        friendship = db.query(models.Friendship).filter(
            ((models.Friendship.requester_id == current_user.id) & (models.Friendship.addressee_id == target_user.id)) |
            ((models.Friendship.requester_id == target_user.id) & (models.Friendship.addressee_id == current_user.id))
        ).first()
        if friendship:
            friend_status = {
                "id": friendship.id,
                "status": friendship.status,
                "is_requester": friendship.requester_id == current_user.id
            }
        
        follow_rel = db.query(models.UserFollow).filter(
            models.UserFollow.follower_id == current_user.id,
            models.UserFollow.followed_id == target_user.id
        ).first()
        if follow_rel:
            is_following = True

    return {
        "user_id": target_user.id,
        "username": target_user.username,
        "is_admin": target_user.is_admin if (current_user and current_user.id == target_user.id) else None,
        "profile": filtered_profile,
        "friendship_status": friend_status,
        "is_following": is_following
    }


@router.put("/profile/me")
def update_my_profile(
    profile_data: schemas.ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    profile = current_user.profile
    if not profile:
        profile = models.UserProfile(user_id=current_user.id)
        db.add(profile)

    if profile_data.display_name is not None:
        profile.display_name = profile_data.display_name.strip() if profile_data.display_name else None

    if profile_data.first_name is not None:
        profile.first_name = profile_data.first_name
    if profile_data.first_name_visibility is not None:
        profile.first_name_visibility = profile_data.first_name_visibility

    if profile_data.last_name is not None:
        profile.last_name = profile_data.last_name
    if profile_data.last_name_visibility is not None:
        profile.last_name_visibility = profile_data.last_name_visibility

    if profile_data.bio is not None:
        profile.bio = profile_data.bio
    if profile_data.bio_visibility is not None:
        profile.bio_visibility = profile_data.bio_visibility

    if profile_data.location is not None:
        profile.location = profile_data.location
    if profile_data.location_visibility is not None:
        profile.location_visibility = profile_data.location_visibility

    if profile_data.birthdate is not None:
        profile.birthdate = profile_data.birthdate
    if profile_data.birthdate_visibility is not None:
        profile.birthdate_visibility = profile_data.birthdate_visibility

    if profile_data.phone is not None:
        profile.phone = profile_data.phone
    if profile_data.phone_visibility is not None:
        profile.phone_visibility = profile_data.phone_visibility

    if profile_data.email is not None:
        clean_email = str(profile_data.email).strip().lower()
        if clean_email != current_user.email.lower():
            existing = db.query(models.User).filter(
                models.User.email == clean_email,
                models.User.id != current_user.id
            ).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email address is already in use by another account."
                )
            current_user.email = clean_email

    if profile_data.email_visibility is not None:
        profile.email_visibility = profile_data.email_visibility

    if profile_data.avatar_url is not None:
        profile.avatar_url = profile_data.avatar_url

    if profile_data.dm_privacy is not None:
        clean_dm = profile_data.dm_privacy.strip().lower()
        if clean_dm in {"anyone", "friends", "none"}:
            profile.dm_privacy = clean_dm

    if profile_data.online_status is not None:
        clean_status = profile_data.online_status.strip().lower()
        if clean_status in {"online", "offline", "unknown"}:
            profile.online_status = clean_status

    if profile_data.online_status_visibility is not None:
        clean_vis = profile_data.online_status_visibility.strip().lower()
        if clean_vis in {"share", "obscure", "public", "friends", "private"}:
            profile.online_status_visibility = clean_vis

    if profile_data.notify_messages is not None:
        profile.notify_messages = bool(profile_data.notify_messages)

    if profile_data.notify_comments is not None:
        profile.notify_comments = bool(profile_data.notify_comments)

    if profile_data.notification_mode is not None:
        clean_mode = profile_data.notification_mode.strip().lower()
        if clean_mode in {"constant", "limited"}:
            profile.notification_mode = clean_mode

    if profile_data.obscure_notification_content is not None:
        profile.obscure_notification_content = bool(profile_data.obscure_notification_content)

    if profile_data.email_notify_messages is not None:
        profile.email_notify_messages = bool(profile_data.email_notify_messages)

    if profile_data.email_notify_comments is not None:
        profile.email_notify_comments = bool(profile_data.email_notify_comments)

    if profile_data.email_notify_posts is not None:
        profile.email_notify_posts = bool(profile_data.email_notify_posts)

    if profile_data.email_notification_frequency is not None:
        clean_freq = profile_data.email_notification_frequency.strip().lower()
        if clean_freq in {"instant", "30min", "hourly", "daily", "never"}:
            profile.email_notification_frequency = clean_freq

    if profile_data.email_obscure_notification_content is not None:
        profile.email_obscure_notification_content = bool(profile_data.email_obscure_notification_content)

    if profile_data.timezone is not None:
        profile.timezone = profile_data.timezone.strip()

    db.commit()
    db.refresh(profile)

    return {"message": "Profile updated successfully", "profile": profile}


@router.post("/profile/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    import os, uuid, io

    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file selected for avatar upload.")

    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        raise HTTPException(status_code=400, detail="Avatar must be an image file (.jpg, .png, .gif, .webp)")

    filename = f"avatar_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    from app import security_utils
    contents = security_utils.strip_exif_data(contents, ext)

    # Scale image down to max 512x512 resolution for fast page loads
    scaled = False
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(contents))
        max_size = (512, 512)

        if img.width > max_size[0] or img.height > max_size[1]:
            if ext in {".jpg", ".jpeg"} and img.mode != "RGB":
                img = img.convert("RGB")

            resample_filter = getattr(Image, "Resampling", Image).LANCZOS
            img.thumbnail(max_size, resample_filter)

            save_format = "JPEG" if ext in {".jpg", ".jpeg"} else (ext.replace(".", "").upper())
            img.save(file_path, format=save_format, optimize=True)
            scaled = True
    except Exception:
        scaled = False

    if not scaled:
        with open(file_path, "wb") as f:
            f.write(contents)

    avatar_url = f"/uploads/{filename}"

    profile = current_user.profile
    if not profile:
        profile = models.UserProfile(user_id=current_user.id)
        db.add(profile)

    profile.avatar_url = avatar_url
    db.commit()

    return {"message": "Avatar uploaded successfully", "avatar_url": avatar_url}



@router.post("/change-password")
def change_password(
    pwd_data: schemas.PasswordChange,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not auth.verify_password(pwd_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect."
        )

    if len(pwd_data.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters long."
        )

    new_hash = auth.get_password_hash(pwd_data.new_password)
    current_user.hashed_password = new_hash
    db.commit()

    return {"message": "Password changed successfully."}


@router.delete("/me")
def delete_my_account(
    payload: Optional[schemas.UserDelete] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Immediate Account Deletion:
    Deletes the current user record. SQLite foreign key cascading immediately purges
    all posts, profile, comments, likes, friendships, group memberships, and email tokens.
    """
    if current_user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The initial system administrator account cannot be deleted."
        )

    if payload and payload.password:
        if not auth.verify_password(payload.password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect password. Account deletion aborted."
            )

    user_id = current_user.id
    username = current_user.username

    db.delete(current_user)
    db.commit()

    return {"message": f"Account for {username} (ID: {user_id}) and all associated data have been permanently deleted."}


@router.post("/friends/request/{target_username}")
def send_friend_request(
    target_username: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    identifier = target_username.strip().lstrip('@').lower()
    target_user = db.query(models.User).filter(
        (models.User.username == identifier) | (models.User.email == identifier)
    ).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot send friend request to yourself")

    existing = db.query(models.Friendship).filter(
        ((models.Friendship.requester_id == current_user.id) & (models.Friendship.addressee_id == target_user.id)) |
        ((models.Friendship.requester_id == target_user.id) & (models.Friendship.addressee_id == current_user.id))
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail=f"Friendship or pending request already exists (status: {existing.status})")

    friendship = models.Friendship(
        requester_id=current_user.id,
        addressee_id=target_user.id,
        status="pending"
    )
    db.add(friendship)
    db.commit()

    return {"message": f"Friend request sent to @{target_user.username}"}


@router.post("/friends/respond/{friendship_id}")
def respond_friend_request(
    friendship_id: int,
    action: str,  # accept or decline
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    friendship = db.query(models.Friendship).filter(models.Friendship.id == friendship_id).first()
    if not friendship:
        raise HTTPException(status_code=404, detail="Friend request not found")

    if friendship.addressee_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only respond to requests sent to you")

    if action == "accept":
        friendship.status = "accepted"
        db.commit()
        return {"message": "Friend request accepted"}
    elif action == "decline":
        db.delete(friendship)
        db.commit()
        return {"message": "Friend request declined"}
    else:
        raise HTTPException(status_code=400, detail="Action must be 'accept' or 'decline'")


@router.get("/friends/list")
def list_friends(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    friendships = db.query(models.Friendship).filter(
        (models.Friendship.status == "accepted") &
        ((models.Friendship.requester_id == current_user.id) | (models.Friendship.addressee_id == current_user.id))
    ).all()

    friends = []
    for f in friendships:
        friend_id = f.addressee_id if f.requester_id == current_user.id else f.requester_id
        friend_user = db.query(models.User).filter(models.User.id == friend_id).first()
        if friend_user:
            f_p = friend_user.profile
            friends.append({
                "friendship_id": f.id,
                "user_id": friend_user.id,
                "username": friend_user.username,
                "display_name": privacy.get_display_name(friend_user),
                "avatar_url": f_p.avatar_url if f_p else None,
                "online_status": privacy.get_online_status(db, current_user.id, friend_user)
            })

    pending_received = db.query(models.Friendship).filter(
        models.Friendship.addressee_id == current_user.id,
        models.Friendship.status == "pending"
    ).all()

    pending_list = []
    for p in pending_received:
        req_user = db.query(models.User).filter(models.User.id == p.requester_id).first()
        if req_user:
            req_p = req_user.profile
            pending_list.append({
                "friendship_id": p.id,
                "user_id": req_user.id,
                "username": req_user.username,
                "display_name": privacy.get_display_name(req_user),
                "avatar_url": req_p.avatar_url if req_p else None
            })

    return {
        "friends": friends,
        "pending_requests": pending_list
    }


@router.post("/{username}/follow")
def toggle_follow_user(
    username: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    target_user = db.query(models.User).filter(models.User.username == username.strip().lower()).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    # Check if they are accepted friends
    friendship = db.query(models.Friendship).filter(
        (models.Friendship.status == "accepted") &
        (
            ((models.Friendship.requester_id == current_user.id) & (models.Friendship.addressee_id == target_user.id)) |
            ((models.Friendship.requester_id == target_user.id) & (models.Friendship.addressee_id == current_user.id))
        )
    ).first()

    if not friendship:
        raise HTTPException(status_code=400, detail="You can only follow users you are friends with")

    existing_follow = db.query(models.UserFollow).filter(
        models.UserFollow.follower_id == current_user.id,
        models.UserFollow.followed_id == target_user.id
    ).first()

    if existing_follow:
        db.delete(existing_follow)
        db.commit()
        return {"is_following": False, "message": f"Unfollowed @{target_user.username}"}
    else:
        follow_rel = models.UserFollow(follower_id=current_user.id, followed_id=target_user.id)
        db.add(follow_rel)
        db.commit()
        return {"is_following": True, "message": f"Now following @{target_user.username}"}

