import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app import models, auth, privacy

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

@router.get("/poll")
def poll_notifications(
    since: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    now_utc = datetime.datetime.utcnow()
    since_dt = now_utc - datetime.timedelta(seconds=60)

    if since:
        try:
            clean_since = since.replace("Z", "+00:00")
            parsed = datetime.datetime.fromisoformat(clean_since)
            if parsed.tzinfo:
                parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            since_dt = parsed
        except Exception:
            pass

    profile = current_user.profile
    notify_messages = getattr(profile, "notify_messages", True)
    if notify_messages is None:
        notify_messages = True

    notify_comments = getattr(profile, "notify_comments", True)
    if notify_comments is None:
        notify_comments = True

    notification_mode = getattr(profile, "notification_mode", "constant") or "constant"
    obscure_notification_content = bool(getattr(profile, "obscure_notification_content", False))

    messages_list = []
    if notify_messages:
        msgs = db.query(models.DirectMessage).filter(
            models.DirectMessage.recipient_id == current_user.id,
            models.DirectMessage.sender_id != current_user.id,
            models.DirectMessage.created_at > since_dt
        ).order_by(models.DirectMessage.created_at.asc()).all()

        for m in msgs:
            sender = m.sender
            sender_profile = sender.profile if sender else None
            messages_list.append({
                "id": m.id,
                "sender_username": sender.username if sender else "Unknown",
                "sender_display_name": (sender_profile.display_name if sender_profile and sender_profile.display_name else sender.username) if sender else "Unknown",
                "content": m.content,
                "created_at": m.created_at.isoformat()
            })

    comments_list = []
    if notify_comments:
        post_cmts = db.query(models.Comment).join(models.Post).filter(
            models.Post.author_id == current_user.id,
            models.Comment.author_id != current_user.id,
            models.Comment.created_at > since_dt
        ).all()

        reply_cmts = db.query(models.Comment).filter(
            models.Comment.parent_id.isnot(None),
            models.Comment.author_id != current_user.id,
            models.Comment.created_at > since_dt
        ).all()
        reply_cmts_for_user = [
            c for c in reply_cmts
            if c.parent and c.parent.author_id == current_user.id
        ]

        all_notif_cmts = {c.id: c for c in (post_cmts + reply_cmts_for_user)}.values()
        sorted_notif_cmts = sorted(all_notif_cmts, key=lambda c: c.created_at or datetime.datetime.min)

        for c in sorted_notif_cmts:
            author = c.author
            author_profile = author.profile if author else None
            is_reply_to_me = bool(c.parent and c.parent.author_id == current_user.id)
            comments_list.append({
                "id": c.id,
                "author_username": author.username if author else "Unknown",
                "author_display_name": (author_profile.display_name if author_profile and author_profile.display_name else author.username) if author else "Unknown",
                "post_id": c.post_id,
                "parent_id": c.parent_id,
                "is_reply": is_reply_to_me,
                "content": c.content,
                "created_at": c.created_at.isoformat()
            })

    posts_list = []
    followed_rows = db.query(models.UserFollow.followed_id).filter(
        models.UserFollow.follower_id == current_user.id
    ).all()
    followed_user_ids = [r[0] for r in followed_rows]

    if followed_user_ids:
        accepted_friendships = db.query(models.Friendship).filter(
            (models.Friendship.status == "accepted") &
            (
                ((models.Friendship.requester_id == current_user.id) & (models.Friendship.addressee_id.in_(followed_user_ids))) |
                ((models.Friendship.addressee_id == current_user.id) & (models.Friendship.requester_id.in_(followed_user_ids)))
            )
        ).all()
        valid_followed_ids = set()
        for f in accepted_friendships:
            valid_followed_ids.add(f.addressee_id if f.requester_id == current_user.id else f.requester_id)

        if valid_followed_ids:
            posts = db.query(models.Post).filter(
                models.Post.author_id.in_(valid_followed_ids),
                models.Post.created_at > since_dt
            ).order_by(models.Post.created_at.asc()).all()

            for p in posts:
                if privacy.can_view_post(db, current_user.id, p):
                    author = p.author
                    author_profile = author.profile if author else None
                    posts_list.append({
                        "id": p.id,
                        "author_username": author.username if author else "Unknown",
                        "author_display_name": (author_profile.display_name if author_profile and author_profile.display_name else author.username) if author else "Unknown",
                        "content": p.content,
                        "created_at": p.created_at.isoformat()
                    })

    likes_list = []
    likes = db.query(models.Like).join(models.Post).filter(
        models.Post.author_id == current_user.id,
        models.Like.user_id != current_user.id,
        models.Like.created_at > since_dt
    ).order_by(models.Like.created_at.asc()).all()

    for l in likes:
        u = l.user
        p = u.profile if u else None
        likes_list.append({
            "id": l.id,
            "user_username": u.username if u else "Unknown",
            "user_display_name": (p.display_name if p and p.display_name else u.username) if u else "Unknown",
            "post_id": l.post_id,
            "created_at": l.created_at.isoformat() if l.created_at else datetime.datetime.utcnow().isoformat()
        })

    return {
        "server_time": now_utc.isoformat(),
        "notify_messages": notify_messages,
        "notify_comments": notify_comments,
        "notification_mode": notification_mode,
        "obscure_notification_content": obscure_notification_content,
        "messages": messages_list,
        "comments": comments_list,
        "posts": posts_list,
        "likes": likes_list
    }


def cleanup_old_activity(db: Session):
    cutoff_dt = datetime.datetime.utcnow() - datetime.timedelta(days=180)
    try:
        db.query(models.Like).filter(models.Like.created_at < cutoff_dt).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()


@router.post("/cleanup")
def cleanup_activity_endpoint(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    cutoff_dt = datetime.datetime.utcnow() - datetime.timedelta(days=180)
    deleted_likes = db.query(models.Like).filter(models.Like.created_at < cutoff_dt).delete(synchronize_session=False)
    db.commit()
    return {"message": f"Deleted activity items older than 180 days ({deleted_likes} likes deleted)."}


@router.get("/activity")
def get_activity_feed(
    filter_type: Optional[str] = Query("all"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    cleanup_old_activity(db)
    cutoff_dt = datetime.datetime.utcnow() - datetime.timedelta(days=180)

    activity_items = []
    f_type = (filter_type or "all").lower().strip()
    fetch_max = offset + limit

    # 1. Post Likes on current_user's posts
    if f_type in ["all", "likes"]:
        likes = db.query(models.Like).join(models.Post).filter(
            models.Post.author_id == current_user.id,
            models.Like.user_id != current_user.id,
            models.Like.created_at >= cutoff_dt
        ).order_by(models.Like.created_at.desc()).limit(fetch_max).all()

        for l in likes:
            u = l.user
            p = u.profile if u else None
            post = l.post
            activity_items.append({
                "id": f"like-{l.id}",
                "type": "like",
                "actor_username": u.username if u else "Unknown",
                "actor_display_name": (p.display_name if p and p.display_name else u.username) if u else "Unknown",
                "actor_avatar_url": p.avatar_url if p else None,
                "post_id": l.post_id,
                "action_text": "liked your post",
                "content": post.content if post else "",
                "created_at": l.created_at.isoformat() if l.created_at else datetime.datetime.utcnow().isoformat()
            })

    # 2. Comments on current_user's posts or replies to current_user's comments
    if f_type in ["all", "comments"]:
        post_cmts = db.query(models.Comment).join(models.Post).filter(
            models.Post.author_id == current_user.id,
            models.Comment.author_id != current_user.id,
            models.Comment.created_at >= cutoff_dt
        ).order_by(models.Comment.created_at.desc()).limit(fetch_max).all()

        reply_cmts = db.query(models.Comment).filter(
            models.Comment.parent_id.isnot(None),
            models.Comment.author_id != current_user.id,
            models.Comment.created_at >= cutoff_dt
        ).order_by(models.Comment.created_at.desc()).limit(fetch_max).all()
        reply_cmts_for_user = [
            c for c in reply_cmts
            if c.parent and c.parent.author_id == current_user.id
        ]

        all_cmts_dict = {c.id: c for c in (post_cmts + reply_cmts_for_user)}
        sorted_cmts = sorted(all_cmts_dict.values(), key=lambda c: c.created_at or datetime.datetime.min, reverse=True)[:fetch_max]

        for c in sorted_cmts:
            u = c.author
            p = u.profile if u else None
            is_reply = bool(c.parent and c.parent.author_id == current_user.id)
            action_text = "replied to your comment" if is_reply else "commented on your post"
            activity_items.append({
                "id": f"comment-{c.id}",
                "type": "comment",
                "actor_username": u.username if u else "Unknown",
                "actor_display_name": (p.display_name if p and p.display_name else u.username) if u else "Unknown",
                "actor_avatar_url": p.avatar_url if p else None,
                "post_id": c.post_id,
                "action_text": action_text,
                "content": c.content,
                "created_at": c.created_at.isoformat() if c.created_at else datetime.datetime.utcnow().isoformat()
            })

    # 3. Direct Messages
    if f_type in ["all", "messages"]:
        msgs = db.query(models.DirectMessage).filter(
            models.DirectMessage.recipient_id == current_user.id,
            models.DirectMessage.sender_id != current_user.id,
            models.DirectMessage.created_at >= cutoff_dt
        ).order_by(models.DirectMessage.created_at.desc()).limit(fetch_max).all()

        for m in msgs:
            u = m.sender
            p = u.profile if u else None
            activity_items.append({
                "id": f"message-{m.id}",
                "type": "message",
                "actor_username": u.username if u else "Unknown",
                "actor_display_name": (p.display_name if p and p.display_name else u.username) if u else "Unknown",
                "actor_avatar_url": p.avatar_url if p else None,
                "action_text": "sent you a message",
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else datetime.datetime.utcnow().isoformat()
            })

    # 4. Friend Activity
    if f_type in ["all", "friends"]:
        friendships = db.query(models.Friendship).filter(
            ((models.Friendship.addressee_id == current_user.id) | (models.Friendship.requester_id == current_user.id)),
            models.Friendship.created_at >= cutoff_dt
        ).order_by(models.Friendship.created_at.desc()).limit(fetch_max).all()

        for f in friendships:
            if f.addressee_id == current_user.id and f.status == "pending":
                u = f.requester
                p = u.profile if u else None
                activity_items.append({
                    "id": f"friend-{f.id}",
                    "type": "friend_request",
                    "actor_username": u.username if u else "Unknown",
                    "actor_display_name": (p.display_name if p and p.display_name else u.username) if u else "Unknown",
                    "actor_avatar_url": p.avatar_url if p else None,
                    "action_text": "sent you a friend request",
                    "content": "",
                    "created_at": f.created_at.isoformat() if f.created_at else datetime.datetime.utcnow().isoformat()
                })
            elif f.status == "accepted":
                other_user = f.requester if f.addressee_id == current_user.id else f.addressee
                p = other_user.profile if other_user else None
                activity_items.append({
                    "id": f"friend-{f.id}",
                    "type": "friend_accept",
                    "actor_username": other_user.username if other_user else "Unknown",
                    "actor_display_name": (p.display_name if p and p.display_name else other_user.username) if other_user else "Unknown",
                    "actor_avatar_url": p.avatar_url if p else None,
                    "action_text": "became friends with you",
                    "content": "",
                    "created_at": f.created_at.isoformat() if f.created_at else datetime.datetime.utcnow().isoformat()
                })

    # Sort all items by created_at descending
    activity_items.sort(key=lambda x: x["created_at"], reverse=True)
    sliced_items = activity_items[offset : offset + limit]

    return {
        "activity": sliced_items,
        "has_more": len(sliced_items) == limit,
        "offset": offset,
        "limit": limit
    }


def process_email_notification_digests(db: Session, force: bool = False) -> dict:
    from app import email
    now_utc = datetime.datetime.utcnow()

    # Query all registered users with valid emails
    users = db.query(models.User).filter(models.User.email != None, models.User.email != "").all()
    sent_count = 0

    for u in users:
        profile = u.profile
        if not profile:
            continue

        email_messages = getattr(profile, "email_notify_messages", True)
        if email_messages is None:
            email_messages = True

        email_comments = getattr(profile, "email_notify_comments", True)
        if email_comments is None:
            email_comments = True

        email_posts = getattr(profile, "email_notify_posts", True)
        if email_posts is None:
            email_posts = True

        freq = getattr(profile, "email_notification_frequency", "30min") or "30min"
        if freq == "never" or (not email_messages and not email_comments and not email_posts):
            continue

        last_sent = profile.last_email_digest_sent
        if last_sent and not force:
            seconds_since = (now_utc - last_sent).total_seconds()
            if freq == "instant" and seconds_since < 5:
                continue
            elif freq in ["30min", "hourly"] and seconds_since < 1800:
                continue
            elif freq == "daily" and seconds_since < 86400:
                continue

        since_dt = last_sent if last_sent else (now_utc - datetime.timedelta(days=30))

        # Gather unread messages
        messages_list = []
        if email_messages:
            msgs = db.query(models.DirectMessage).filter(
                models.DirectMessage.recipient_id == u.id,
                models.DirectMessage.sender_id != u.id,
                models.DirectMessage.created_at > since_dt,
                models.DirectMessage.is_read == False
            ).order_by(models.DirectMessage.created_at.asc()).all()

            for m in msgs:
                sender = m.sender
                sender_profile = sender.profile if sender else None
                messages_list.append({
                    "id": m.id,
                    "sender_username": sender.username if sender else "Unknown",
                    "sender_display_name": (sender_profile.display_name if sender_profile and sender_profile.display_name else sender.username) if sender else "Unknown",
                    "content": m.content
                })

        comments_list = []
        if email_comments:
            post_cmts = db.query(models.Comment).join(models.Post).filter(
                models.Post.author_id == u.id,
                models.Comment.author_id != u.id,
                models.Comment.created_at > since_dt
            ).all()

            reply_cmts = db.query(models.Comment).filter(
                models.Comment.parent_id.isnot(None),
                models.Comment.author_id != u.id,
                models.Comment.created_at > since_dt
            ).all()
            reply_cmts_for_user = [
                c for c in reply_cmts
                if c.parent and c.parent.author_id == u.id
            ]

            all_notif_cmts = {c.id: c for c in (post_cmts + reply_cmts_for_user)}.values()
            sorted_notif_cmts = sorted(all_notif_cmts, key=lambda c: c.created_at or datetime.datetime.min)

            for c in sorted_notif_cmts:
                author = c.author
                author_profile = author.profile if author else None
                is_reply_to_me = bool(c.parent and c.parent.author_id == u.id)
                comments_list.append({
                    "id": c.id,
                    "post_id": c.post_id,
                    "parent_id": c.parent_id,
                    "is_reply": is_reply_to_me,
                    "author_username": author.username if author else "Unknown",
                    "author_display_name": (author_profile.display_name if author_profile and author_profile.display_name else author.username) if author else "Unknown",
                    "content": c.content
                })

        # Gather posts from followed friends
        posts_list = []
        followed_rows = db.query(models.UserFollow.followed_id).filter(
            models.UserFollow.follower_id == u.id
        ).all()
        followed_user_ids = [r[0] for r in followed_rows]

        if followed_user_ids:
            accepted_friendships = db.query(models.Friendship).filter(
                (models.Friendship.status == "accepted") &
                (
                    ((models.Friendship.requester_id == u.id) & (models.Friendship.addressee_id.in_(followed_user_ids))) |
                    ((models.Friendship.addressee_id == u.id) & (models.Friendship.requester_id.in_(followed_user_ids)))
                )
            ).all()
            valid_followed_ids = set()
            for f in accepted_friendships:
                valid_followed_ids.add(f.addressee_id if f.requester_id == u.id else f.requester_id)

            if valid_followed_ids:
                p_items = db.query(models.Post).filter(
                    models.Post.author_id.in_(valid_followed_ids),
                    models.Post.created_at > since_dt
                ).order_by(models.Post.created_at.asc()).all()

                for p in p_items:
                    if privacy.can_view_post(db, u.id, p):
                        author = p.author
                        author_profile = author.profile if author else None
                        posts_list.append({
                            "id": p.id,
                            "author_username": author.username if author else "Unknown",
                            "author_display_name": (author_profile.display_name if author_profile and author_profile.display_name else author.username) if author else "Unknown",
                            "content": p.content
                        })

        total_updates = len(messages_list) + len(comments_list) + len(posts_list)
        if total_updates > 0:
            obscure = bool(getattr(profile, "email_obscure_notification_content", False))
            success = email.send_batch_digest_email(
                user_email=u.email,
                username=u.username,
                messages=messages_list,
                comments=comments_list,
                posts=posts_list,
                obscure=obscure,
                db=db
            )
            # Update last_email_digest_sent and commit
            profile.last_email_digest_sent = now_utc
            db.commit()
            if success:
                sent_count += 1

    return {"message": "Processed email notification digests", "emails_sent": sent_count}


@router.post("/send-email-digest")
def trigger_email_digest(
    force: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return process_email_notification_digests(db, force=force)
