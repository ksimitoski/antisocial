import os
import uuid
import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List, Optional, Union

from app.database import get_db
from app import models, schemas, auth, privacy, security_utils

router = APIRouter(prefix="/api/posts", tags=["Posts"])

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_post(
    content: Optional[str] = Form(None),
    visibility: Optional[str] = Form("public"),
    group_id: Optional[Union[int, str]] = Form(None),
    expires_in: Optional[str] = Form(None),  # 'none', '1h', '24h', '7d'
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if content and len(content) > 10000:
        raise HTTPException(
            status_code=400,
            detail="Post content must be 10,000 characters or less"
        )

    clean_content = content.strip() if content and content.strip() else ""

    parsed_group_id = None
    if group_id is not None:
        try:
            s_gid = str(group_id).strip()
            if s_gid and s_gid.isdigit():
                parsed_group_id = int(s_gid)
        except (ValueError, TypeError):
            pass

    if parsed_group_id:
        visibility = "group"
        if not privacy.is_group_member(db, parsed_group_id, current_user.id) and not privacy.is_admin_or_moderator(db, current_user.id):
            raise HTTPException(status_code=403, detail="You must be a member or admin/moderator of the group to post in it")

    if visibility == "group":
        if not parsed_group_id:
            raise HTTPException(status_code=400, detail="group_id is required for group visibility")
        if not privacy.is_group_member(db, parsed_group_id, current_user.id) and not privacy.is_admin_or_moderator(db, current_user.id):
            raise HTTPException(status_code=403, detail="You must be a member or admin/moderator of the group to post in it")

    media_type = "none"
    media_url = None

    if file and file.filename and file.filename.strip():
        ext = os.path.splitext(file.filename)[1].lower()
        if ext in ALLOWED_IMAGE_EXT:
            media_type = "image"
        else:
            raise HTTPException(
                status_code=400,
                detail="The selected file format is not supported. Only image attachments are accepted."
            )

        if media_type != "none":
            filename = f"{uuid.uuid4().hex}{ext}"
            file_path = os.path.join(UPLOAD_DIR, filename)

            contents = await file.read()
            clean_contents = security_utils.strip_exif_data(contents, ext)
            with open(file_path, "wb") as f:
                f.write(clean_contents)

            media_url = f"/uploads/{filename}"

    expires_at = None
    if expires_in and expires_in.strip().lower() != "none":
        clean_exp = expires_in.strip().lower()
        now = datetime.datetime.utcnow()
        if clean_exp == "1h":
            expires_at = now + datetime.timedelta(hours=1)
        elif clean_exp == "24h":
            expires_at = now + datetime.timedelta(hours=24)
        elif clean_exp == "7d":
            expires_at = now + datetime.timedelta(days=7)

    post = models.Post(
        author_id=current_user.id,
        group_id=parsed_group_id,
        content=clean_content,
        media_type=media_type,
        media_url=media_url,
        visibility=visibility,
        expires_at=expires_at
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    return {
        "message": "Post created successfully",
        "post_id": post.id,
        "media_type": post.media_type,
        "media_url": post.media_url,
        "visibility": post.visibility
    }


@router.get("")
def get_feed(
    username: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    group_id: Optional[str] = Query(None),
    skip: int = Query(0),
    limit: int = Query(50),
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional)
):
    parsed_group_id = None
    if group_id is not None:
        try:
            s_gid = str(group_id).strip()
            if s_gid and s_gid.isdigit():
                parsed_group_id = int(s_gid)
        except (ValueError, TypeError):
            pass

    now = datetime.datetime.utcnow()
    db.query(models.Post).filter(
        models.Post.expires_at.isnot(None),
        models.Post.expires_at <= now
    ).delete(synchronize_session=False)
    db.commit()

    query = db.query(models.Post).filter(
        or_(models.Post.expires_at.is_(None), models.Post.expires_at > now)
    )

    if search and search.strip():
        query = query.filter(models.Post.content.ilike(f"%{search.strip()}%"))

    if username and username.strip():
        clean_user = username.strip().lstrip('@')
        matching_user_ids = [
            u.id for u in db.query(models.User).filter(
                models.User.username.ilike(f"%{clean_user}%")
            ).all()
        ]
        if not matching_user_ids:
            return []
        query = query.filter(models.Post.author_id.in_(matching_user_ids))

    if parsed_group_id:
        viewer_id = current_user.id if current_user else None
        if not viewer_id or (not privacy.is_group_member(db, parsed_group_id, viewer_id) and not privacy.is_admin_or_moderator(db, viewer_id)):
            return []
        query = query.filter(models.Post.group_id == parsed_group_id)

    all_posts = query.order_by(models.Post.created_at.desc()).all()

    viewer_id = current_user.id if current_user else None

    # Enforce fine-grained privacy filtering:
    # Only return posts that viewer_id has explicit rights to see
    visible_posts = []
    for post in all_posts:
        if privacy.can_view_post(db, viewer_id, post):
            author_profile = post.author.profile
            avatar = author_profile.avatar_url if author_profile else None
            display_name = privacy.get_display_name(post.author)
            
            likes_count = len(post.likes)
            user_has_liked = any(l.user_id == viewer_id for l in post.likes) if viewer_id else False

            comments_data = []
            sorted_comments = sorted(
                post.comments,
                key=lambda c: (c.created_at or datetime.datetime.min, c.id or 0),
                reverse=True
            )
            for c in sorted_comments:
                c_avatar = c.author.profile.avatar_url if c.author.profile else None
                c_display_name = privacy.get_display_name(c.author)
                comments_data.append({
                    "id": c.id,
                    "parent_id": c.parent_id,
                    "author_id": c.author_id,
                    "author_username": c.author.username,
                    "author_display_name": c.display_name if hasattr(c, 'display_name') else c_display_name,
                    "author_avatar": c_avatar,
                    "content": c.content,
                    "created_at": c.created_at
                })

            visible_posts.append({
                "id": post.id,
                "author_id": post.author_id,
                "author_username": post.author.username,
                "author_display_name": display_name,
                "author_avatar": avatar,
                "author_online_status": privacy.get_online_status(db, current_user.id if current_user else None, post.author),
                "group_id": post.group_id,
                "group_name": post.group.name if post.group else None,
                "content": post.content,
                "media_type": post.media_type,
                "media_url": post.media_url,
                "visibility": post.visibility,
                "created_at": post.created_at,
                "likes_count": likes_count,
                "user_has_liked": user_has_liked,
                "comments": comments_data
            })


    return visible_posts[skip:skip + limit]


@router.get("/{post_id}")
def get_single_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional)
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    viewer_id = current_user.id if current_user else None
    if not privacy.can_view_post(db, viewer_id, post):
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to view this post due to privacy settings"
        )

    author_profile = post.author.profile
    avatar = author_profile.avatar_url if author_profile else None
    display_name = privacy.get_display_name(post.author)
    author_online_status = privacy.get_online_status(db, viewer_id, post.author)

    likes_count = len(post.likes)
    user_has_liked = any(l.user_id == viewer_id for l in post.likes) if viewer_id else False

    comments_data = []
    sorted_comments = sorted(
        post.comments,
        key=lambda c: (c.created_at or datetime.datetime.min, c.id or 0),
        reverse=True
    )
    for c in sorted_comments:
        c_avatar = c.author.profile.avatar_url if c.author.profile else None
        c_display_name = privacy.get_display_name(c.author)
        comments_data.append({
            "id": c.id,
            "parent_id": c.parent_id,
            "author_id": c.author_id,
            "author_username": c.author.username,
            "author_display_name": c.display_name if hasattr(c, 'display_name') else c_display_name,
            "author_avatar": c_avatar,
            "content": c.content,
            "created_at": c.created_at
        })

    group_name = post.group.name if post.group else None

    return {
        "id": post.id,
        "author_id": post.author_id,
        "author_username": post.author.username,
        "author_display_name": display_name,
        "author_avatar": avatar,
        "author_online_status": author_online_status,
        "content": post.content,
        "media_url": post.media_url,
        "media_type": post.media_type,
        "visibility": post.visibility,
        "group_id": post.group_id,
        "group_name": group_name,
        "likes_count": likes_count,
        "user_has_liked": user_has_liked,
        "comments": comments_data,
        "created_at": post.created_at
    }


@router.delete("/{post_id}")
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.author_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="You can only delete your own posts")

    db.delete(post)
    db.commit()
    return {"message": "Post deleted successfully"}


@router.put("/{post_id}/privacy")
def update_post_privacy(
    post_id: int,
    privacy_data: schemas.PostPrivacyUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # STRICT SECURITY RULE: ONLY the post author can change post privacy settings.
    # Administrators and moderators cannot change privacy settings for posts written by others.
    if post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the post author can change the privacy settings of this post")

    new_vis = privacy_data.visibility.strip().lower()
    if post.group_id:
        if new_vis != "group":
            raise HTTPException(status_code=400, detail="Group posts must maintain group visibility")
    else:
        valid_visibilities = {"public", "friends", "internal", "internal-only", "private"}
        if new_vis not in valid_visibilities:
            raise HTTPException(status_code=400, detail=f"Invalid visibility mode '{new_vis}'. Must be one of {valid_visibilities}")

    post.visibility = new_vis
    db.commit()
    db.refresh(post)

    return {
        "message": "Post privacy setting updated successfully",
        "post_id": post.id,
        "visibility": post.visibility
    }


@router.put("/{post_id}")
def update_post(
    post_id: int,
    post_data: schemas.PostUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # STRICT SECURITY RULE: ONLY the user that created the post is capable of editing it.
    if post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the user who created this post can edit it")

    if post_data.content is not None:
        if len(post_data.content) > 10000:
            raise HTTPException(status_code=400, detail="Post content must be 10,000 characters or less")
        clean_content = post_data.content.strip()
        if not clean_content and not post.media_url:
            raise HTTPException(status_code=400, detail="Post content cannot be empty")
        post.content = clean_content

    if post_data.visibility is not None:
        new_vis = post_data.visibility.strip().lower()
        if post.group_id:
            if new_vis != "group":
                raise HTTPException(status_code=400, detail="Group posts must maintain group visibility")
        else:
            valid_visibilities = {"public", "friends", "internal", "private"}
            if new_vis in valid_visibilities:
                post.visibility = new_vis

    db.commit()
    db.refresh(post)

    return {
        "message": "Post updated successfully",
        "id": post.id,
        "content": post.content,
        "visibility": post.visibility
    }


@router.post("/{post_id}/like")
def toggle_like(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if not privacy.can_view_post(db, current_user.id, post):
        raise HTTPException(status_code=403, detail="Not authorized to interact with this post")

    existing_like = db.query(models.Like).filter(
        models.Like.post_id == post_id,
        models.Like.user_id == current_user.id
    ).first()

    if existing_like:
        db.delete(existing_like)
        db.commit()
        liked = False
    else:
        new_like = models.Like(post_id=post_id, user_id=current_user.id)
        db.add(new_like)
        db.commit()
        liked = True

    likes_count = db.query(models.Like).filter(models.Like.post_id == post_id).count()
    return {"liked": liked, "likes_count": likes_count}


@router.post("/{post_id}/comments")
def add_comment(
    post_id: int,
    comment_data: schemas.CommentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if not privacy.can_view_post(db, current_user.id, post):
        raise HTTPException(status_code=403, detail="Not authorized to interact with this post")

    effective_parent_id = None
    if comment_data.content and len(comment_data.content) > 280:
        raise HTTPException(status_code=400, detail="Comment must be 280 characters or less")

    content = (comment_data.content or "").strip()

    if comment_data.parent_id:
        parent_comment = db.query(models.Comment).filter(
            models.Comment.id == comment_data.parent_id,
            models.Comment.post_id == post_id
        ).first()
        if not parent_comment:
            raise HTTPException(status_code=404, detail="Parent comment not found")

        effective_parent_id = parent_comment.id
        parent_author_username = parent_comment.author.username
        mention_prefix = f"@{parent_author_username}:"

        # If replying to a reply, ensure @username: prefix is present
        if parent_comment.parent_id or not content.lower().startswith(mention_prefix.lower()):
            if not content.lower().startswith(mention_prefix.lower()) and not content.lower().startswith(f"@{parent_author_username.lower()} "):
                content = f"{mention_prefix} {content}"

    if len(content) > 280:
        raise HTTPException(status_code=400, detail="Comment must be 280 characters or less")

    comment = models.Comment(
        post_id=post_id,
        author_id=current_user.id,
        parent_id=effective_parent_id,
        content=content
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    author_profile = current_user.profile
    avatar_url = author_profile.avatar_url if author_profile else None
    display_name = privacy.get_display_name(current_user)

    return {
        "id": comment.id,
        "post_id": post_id,
        "parent_id": comment.parent_id,
        "author_id": current_user.id,
        "author_username": current_user.username,
        "author_display_name": display_name,
        "author_avatar": avatar_url,
        "content": comment.content,
        "created_at": comment.created_at
    }


@router.delete("/{post_id}")
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    is_mod_or_admin = current_user.is_admin or (current_user.role in ["admin", "moderator"])
    if post.author_id != current_user.id and not is_mod_or_admin:
        raise HTTPException(status_code=403, detail="You do not have permission to delete this post.")

    db.delete(post)
    db.commit()
    return {"message": "Post deleted successfully"}


@router.delete("/{post_id}/comments/{comment_id}")
def delete_comment(
    post_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    comment = db.query(models.Comment).filter(
        models.Comment.id == comment_id,
        models.Comment.post_id == post_id
    ).first()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    is_mod_or_admin = current_user.is_admin or (current_user.role in ["admin", "moderator"])
    is_comment_author = comment.author_id == current_user.id
    is_post_author = comment.post.author_id == current_user.id if comment.post else False

    if not (is_comment_author or is_post_author or is_mod_or_admin):
        raise HTTPException(status_code=403, detail="You do not have permission to delete this comment.")

    db.delete(comment)
    db.commit()
    return {"message": "Comment deleted successfully"}


