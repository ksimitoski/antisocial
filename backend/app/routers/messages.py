from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc, func
import datetime

from app.database import get_db
from app import models, schemas, auth, privacy

router = APIRouter(prefix="/api/messages", tags=["Messages"])


@router.post("", status_code=status.HTTP_201_CREATED)
def send_message(
    msg_data: schemas.DirectMessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    clean_recipient = msg_data.recipient_username.strip().lstrip('@')
    recipient = db.query(models.User).filter(models.User.username.ilike(clean_recipient)).first()
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient user not found")

    if recipient.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot send direct messages to yourself")

    clean_content = msg_data.content.strip()
    if not clean_content:
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    # Enforce Recipient's DM Privacy Settings
    recip_profile = recipient.profile
    dm_setting = (recip_profile.dm_privacy if recip_profile and recip_profile.dm_privacy else "friends").lower()

    if dm_setting == "none":
        raise HTTPException(status_code=403, detail="This user has disabled direct messaging")

    if dm_setting == "friends":
        if not privacy.is_friends(db, current_user.id, recipient.id):
            raise HTTPException(status_code=403, detail="This user only accepts direct messages from friends")

    # Setting 'anyone' allows all logged in users

    # Purge expired DMs across the platform
    now = datetime.datetime.utcnow()
    db.query(models.DirectMessage).filter(
        models.DirectMessage.expires_at.isnot(None),
        models.DirectMessage.expires_at <= now
    ).delete(synchronize_session=False)
    db.commit()

    # Calculate expiration timestamp
    expires_at = None
    if msg_data.expires_in and msg_data.expires_in.strip().lower() != "none":
        clean_exp = msg_data.expires_in.strip().lower()
        if clean_exp == "1h":
            expires_at = now + datetime.timedelta(hours=1)
        elif clean_exp == "24h":
            expires_at = now + datetime.timedelta(hours=24)
        elif clean_exp == "7d":
            expires_at = now + datetime.timedelta(days=7)

    dm = models.DirectMessage(
        sender_id=current_user.id,
        recipient_id=recipient.id,
        content=clean_content,
        is_read=False,
        is_encrypted=msg_data.is_encrypted or False,
        expires_at=expires_at
    )
    db.add(dm)
    db.commit()
    db.refresh(dm)

    sender_avatar = current_user.profile.avatar_url if current_user.profile else None

    return {
        "id": dm.id,
        "sender_id": dm.sender_id,
        "sender_username": current_user.username,
        "sender_display_name": privacy.get_display_name(current_user),
        "sender_avatar": sender_avatar,
        "recipient_id": dm.recipient_id,
        "recipient_username": recipient.username,
        "recipient_display_name": privacy.get_display_name(recipient),
        "content": dm.content,
        "is_read": dm.is_read,
        "is_encrypted": dm.is_encrypted,
        "expires_at": dm.expires_at,
        "created_at": dm.created_at
    }


@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    count = db.query(models.DirectMessage).filter(
        models.DirectMessage.recipient_id == current_user.id,
        models.DirectMessage.is_read == False
    ).count()
    return {"unread_count": count}


@router.get("/conversations")
def get_conversations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Get a list of all conversations for current user with latest message and unread count.
    """
    now = datetime.datetime.utcnow()
    db.query(models.DirectMessage).filter(
        models.DirectMessage.expires_at.isnot(None),
        models.DirectMessage.expires_at <= now
    ).delete(synchronize_session=False)
    db.commit()

    # Fetch all direct messages involving current_user
    all_dms = db.query(models.DirectMessage).filter(
        or_(
            models.DirectMessage.sender_id == current_user.id,
            models.DirectMessage.recipient_id == current_user.id
        )
    ).order_by(desc(models.DirectMessage.created_at)).all()

    partner_map = {}

    for msg in all_dms:
        partner_id = msg.recipient_id if msg.sender_id == current_user.id else msg.sender_id
        if partner_id not in partner_map:
            partner_user = db.query(models.User).filter(models.User.id == partner_id).first()
            if not partner_user:
                continue

            # Calculate unread count for this specific partner
            unread_c = db.query(models.DirectMessage).filter(
                models.DirectMessage.sender_id == partner_id,
                models.DirectMessage.recipient_id == current_user.id,
                models.DirectMessage.is_read == False
            ).count()

            p_profile = partner_user.profile
            partner_map[partner_id] = {
                "partner_id": partner_id,
                "partner_username": partner_user.username,
                "partner_display_name": privacy.get_display_name(partner_user),
                "partner_avatar": p_profile.avatar_url if p_profile else None,
                "online_status": privacy.get_online_status(db, current_user.id, partner_user),
                "last_message": msg.content,
                "last_message_time": msg.created_at,
                "unread_count": unread_c
            }

    conversations = list(partner_map.values())
    conversations.sort(key=lambda x: x["last_message_time"], reverse=True)
    return conversations


@router.get("/conversations/{partner_id}")
def get_conversation_history(
    partner_id: int,
    q: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    before_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    partner = db.query(models.User).filter(models.User.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.datetime.utcnow()
    db.query(models.DirectMessage).filter(
        models.DirectMessage.expires_at.isnot(None),
        models.DirectMessage.expires_at <= now
    ).delete(synchronize_session=False)
    db.commit()

    # Automatically mark incoming unread messages as read
    db.query(models.DirectMessage).filter(
        models.DirectMessage.sender_id == partner_id,
        models.DirectMessage.recipient_id == current_user.id,
        models.DirectMessage.is_read == False
    ).update({"is_read": True}, synchronize_session=False)
    db.commit()

    query_filter = or_(
        and_(models.DirectMessage.sender_id == current_user.id, models.DirectMessage.recipient_id == partner_id),
        and_(models.DirectMessage.sender_id == partner_id, models.DirectMessage.recipient_id == current_user.id)
    )

    if q and q.strip():
        query_filter = and_(query_filter, models.DirectMessage.content.ilike(f"%{q.strip()}%"))

    if before_id:
        query_filter = and_(query_filter, models.DirectMessage.id < before_id)

    # Order by ID descending to get the latest messages up to limit, then reverse to chronological order
    messages = db.query(models.DirectMessage).filter(query_filter).order_by(models.DirectMessage.id.desc()).limit(limit).all()
    messages.reverse()

    results = []
    for m in messages:
        sender_p = m.sender.profile if m.sender else None
        results.append({
            "id": m.id,
            "sender_id": m.sender_id,
            "sender_username": m.sender.username if m.sender else "Unknown",
            "sender_display_name": privacy.get_display_name(m.sender) if m.sender else "Unknown",
            "sender_avatar": sender_p.avatar_url if sender_p else None,
            "recipient_id": m.recipient_id,
            "content": m.content,
            "is_read": m.is_read,
            "expires_at": m.expires_at,
            "created_at": m.created_at
        })

    partner_profile = partner.profile
    return {
        "partner": {
            "id": partner.id,
            "username": partner.username,
            "display_name": privacy.get_display_name(partner),
            "avatar_url": partner_profile.avatar_url if partner_profile else None,
            "online_status": privacy.get_online_status(db, current_user.id, partner)
        },
        "messages": results
    }
