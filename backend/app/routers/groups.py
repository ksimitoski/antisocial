from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth, privacy

router = APIRouter(prefix="/api/groups", tags=["Groups"])

@router.post("", status_code=status.HTTP_201_CREATED)
def create_group(
    group_data: schemas.GroupCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    group = models.Group(
        name=group_data.name.strip(),
        description=group_data.description.strip() if group_data.description else None,
        creator_id=current_user.id,
        is_private=group_data.is_private
    )
    db.add(group)
    db.commit()
    db.refresh(group)

    # Automatically add creator as group admin member
    member = models.GroupMember(
        group_id=group.id,
        user_id=current_user.id,
        role="admin"
    )
    db.add(member)
    db.commit()

    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "creator_id": group.creator_id,
        "is_private": group.is_private,
        "created_at": group.created_at
    }


@router.get("")
def list_groups(
    search: Optional[str] = None,
    skip: int = Query(0),
    limit: int = Query(50),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    query = db.query(models.Group)
    if search and search.strip():
        search_term = f"%{search.strip()}%"
        query = query.filter(
            (models.Group.name.ilike(search_term)) | (models.Group.description.ilike(search_term))
        )
    groups = query.order_by(models.Group.created_at.desc()).all()
    results = []

    for g in groups:
        is_banned = privacy.is_group_banned(db, g.id, current_user.id)
        if is_banned:
            continue

        is_member = privacy.is_group_member(db, g.id, current_user.id)
        has_requested = False
        if not is_member:
            req = db.query(models.GroupJoinRequest).filter(
                models.GroupJoinRequest.group_id == g.id,
                models.GroupJoinRequest.user_id == current_user.id
            ).first()
            has_requested = req is not None

        results.append({
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "creator_id": g.creator_id,
            "creator_username": g.creator.username,
            "member_count": len(g.members),
            "is_member": is_member,
            "is_private": g.is_private or False,
            "has_requested_join": has_requested,
            "is_banned": is_banned
        })

    return results[skip:skip + limit]


@router.get("/{group_id}")
def get_group_details(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    is_banned = privacy.is_group_banned(db, group_id, current_user.id)
    if is_banned:
        raise HTTPException(status_code=403, detail="You are banned from this group")

    is_admin = privacy.is_group_admin(db, group_id, current_user.id)
    is_creator = group.creator_id == current_user.id
    is_member = privacy.is_group_member(db, group_id, current_user.id)
    is_staff = privacy.is_admin_or_moderator(db, current_user.id)

    members = []
    if is_member or is_admin or is_staff:
        for m in group.members:
            m_profile = m.user.profile
            m_avatar = m_profile.avatar_url if m_profile else None
            m_display_name = privacy.get_display_name(m.user)
            members.append({
                "user_id": m.user_id,
                "username": m.user.username,
                "display_name": m_display_name,
                "avatar_url": m_avatar,
                "role": m.role,
                "joined_at": m.joined_at
            })

    join_requests = []
    bans = []
    if is_admin:
        for req in group.join_requests:
            req_user = req.user
            req_profile = req_user.profile if req_user else None
            join_requests.append({
                "user_id": req.user_id,
                "username": req_user.username if req_user else "Unknown",
                "display_name": privacy.get_display_name(req_user) if req_user else "Unknown",
                "avatar_url": req_profile.avatar_url if req_profile else None,
                "requested_at": req.created_at
            })

        for b in group.bans:
            b_user = b.user
            bans.append({
                "user_id": b.user_id,
                "username": b_user.username if b_user else "Unknown",
                "display_name": privacy.get_display_name(b_user) if b_user else "Unknown",
                "banned_at": b.created_at
            })

    req_entry = db.query(models.GroupJoinRequest).filter(
        models.GroupJoinRequest.group_id == group_id,
        models.GroupJoinRequest.user_id == current_user.id
    ).first()

    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "creator_id": group.creator_id,
        "creator_username": group.creator.username,
        "is_private": group.is_private or False,
        "is_member": is_member,
        "is_admin": is_admin,
        "is_staff": is_staff,
        "is_creator": is_creator,
        "is_banned": is_banned,
        "has_requested_join": req_entry is not None,
        "member_count": len(group.members),
        "members": members,
        "join_requests": join_requests,
        "bans": bans
    }


@router.put("/{group_id}")
def update_group(
    group_id: int,
    group_data: schemas.GroupUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if not privacy.is_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only group administrators can edit group settings")

    if group_data.name is not None and group_data.name.strip():
        group.name = group_data.name.strip()

    if group_data.description is not None:
        group.description = group_data.description.strip()

    if group_data.is_private is not None:
        group.is_private = group_data.is_private

    db.commit()
    db.refresh(group)

    return {
        "message": "Group settings updated successfully",
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "is_private": group.is_private
    }


@router.delete("/{group_id}")
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    is_creator = group.creator_id == current_user.id
    is_staff = privacy.is_admin_or_moderator(db, current_user.id)

    if not (is_creator or is_staff):
        raise HTTPException(status_code=403, detail="Only the group creator or system staff can delete this group")

    db.delete(group)
    db.commit()

    return {"message": f"Group '{group.name}' has been deleted successfully"}



@router.post("/{group_id}/join")
def join_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if privacy.is_group_banned(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="You are banned from this group")

    if privacy.is_group_member(db, group_id, current_user.id):
        raise HTTPException(status_code=400, detail="Already a member of this group")

    if group.is_private:
        existing_req = db.query(models.GroupJoinRequest).filter(
            models.GroupJoinRequest.group_id == group_id,
            models.GroupJoinRequest.user_id == current_user.id
        ).first()

        if not existing_req:
            req = models.GroupJoinRequest(group_id=group_id, user_id=current_user.id)
            db.add(req)
            db.commit()

        return {"message": f"Join request sent for group '{group.name}'", "status": "requested"}

    member = models.GroupMember(
        group_id=group_id,
        user_id=current_user.id,
        role="member"
    )
    db.add(member)

    # Clean up any residual join request
    db.query(models.GroupJoinRequest).filter(
        models.GroupJoinRequest.group_id == group_id,
        models.GroupJoinRequest.user_id == current_user.id
    ).delete()

    db.commit()

    return {"message": f"Successfully joined group '{group.name}'", "status": "joined"}


@router.post("/{group_id}/leave")
def leave_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if group.creator_id == current_user.id:
        raise HTTPException(status_code=400, detail="As the group creator, you cannot leave your own group")

    member = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id,
        models.GroupMember.user_id == current_user.id
    ).first()

    if not member:
        raise HTTPException(status_code=400, detail="You are not a member of this group")

    db.delete(member)
    db.commit()

    return {"message": "Successfully left the group"}


@router.get("/{group_id}/requests")
def list_join_requests(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not privacy.is_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only group admins can view join requests")

    requests = db.query(models.GroupJoinRequest).filter(models.GroupJoinRequest.group_id == group_id).all()
    results = []
    for r in requests:
        user_profile = r.user.profile if r.user else None
        results.append({
            "user_id": r.user_id,
            "username": r.user.username if r.user else "Unknown",
            "display_name": privacy.get_display_name(r.user) if r.user else "Unknown",
            "avatar_url": user_profile.avatar_url if user_profile else None,
            "requested_at": r.created_at
        })

    return results


@router.post("/{group_id}/requests/{target_user_id}/approve")
def approve_join_request(
    group_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not privacy.is_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only group admins can approve join requests")

    req = db.query(models.GroupJoinRequest).filter(
        models.GroupJoinRequest.group_id == group_id,
        models.GroupJoinRequest.user_id == target_user_id
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="Join request not found")

    if not privacy.is_group_member(db, group_id, target_user_id):
        member = models.GroupMember(group_id=group_id, user_id=target_user_id, role="member")
        db.add(member)

    db.delete(req)
    db.commit()

    return {"message": "Join request approved"}


@router.post("/{group_id}/requests/{target_user_id}/reject")
def reject_join_request(
    group_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not privacy.is_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only group admins can reject join requests")

    db.query(models.GroupJoinRequest).filter(
        models.GroupJoinRequest.group_id == group_id,
        models.GroupJoinRequest.user_id == target_user_id
    ).delete()
    db.commit()

    return {"message": "Join request rejected"}


@router.post("/{group_id}/invite")
def invite_user_to_group(
    group_id: int,
    invite_data: schemas.GroupInvite,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not privacy.is_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only group admins can invite members")

    target_user = db.query(models.User).filter(
        (models.User.username.ilike(invite_data.username.strip().lstrip('@'))) |
        (models.User.email.ilike(invite_data.username.strip()))
    ).first()

    if not target_user:
        raise HTTPException(status_code=440 if False else 404, detail="User not found")

    # Remove ban if previously banned when explicitly invited by admin
    db.query(models.GroupBan).filter(
        models.GroupBan.group_id == group_id,
        models.GroupBan.user_id == target_user.id
    ).delete()

    if not privacy.is_group_member(db, group_id, target_user.id):
        member = models.GroupMember(group_id=group_id, user_id=target_user.id, role="member")
        db.add(member)

    db.query(models.GroupJoinRequest).filter(
        models.GroupJoinRequest.group_id == group_id,
        models.GroupJoinRequest.user_id == target_user.id
    ).delete()

    db.commit()

    return {"message": f"User '@{target_user.username}' added to group successfully"}


@router.delete("/{group_id}/members/{target_user_id}")
def remove_group_member(
    group_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if not privacy.is_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only group admins can remove members")

    if target_user_id == group.creator_id:
        raise HTTPException(status_code=400, detail="Cannot remove the original group creator")

    db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id,
        models.GroupMember.user_id == target_user_id
    ).delete()

    db.commit()

    return {"message": "User removed from group"}


@router.post("/{group_id}/ban/{target_user_id}")
def ban_user_from_group(
    group_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if not privacy.is_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only group admins can ban users")

    if target_user_id == group.creator_id:
        raise HTTPException(status_code=400, detail="Cannot ban the original group creator")

    # Remove membership
    db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id,
        models.GroupMember.user_id == target_user_id
    ).delete()

    # Remove pending join requests
    db.query(models.GroupJoinRequest).filter(
        models.GroupJoinRequest.group_id == group_id,
        models.GroupJoinRequest.user_id == target_user_id
    ).delete()

    # Add ban entry if not exists
    existing_ban = db.query(models.GroupBan).filter(
        models.GroupBan.group_id == group_id,
        models.GroupBan.user_id == target_user_id
    ).first()

    if not existing_ban:
        ban = models.GroupBan(
            group_id=group_id,
            user_id=target_user_id,
            banned_by_id=current_user.id
        )
        db.add(ban)

    db.commit()

    return {"message": "User banned from group successfully"}


@router.post("/{group_id}/unban/{target_user_id}")
def unban_user_from_group(
    group_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not privacy.is_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only group admins can unban users")

    db.query(models.GroupBan).filter(
        models.GroupBan.group_id == group_id,
        models.GroupBan.user_id == target_user_id
    ).delete()

    db.commit()

    return {"message": "User unbanned from group"}


@router.get("/{group_id}/bans")
def list_group_bans(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not privacy.is_group_admin(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only group admins can view banned users")

    bans = db.query(models.GroupBan).filter(models.GroupBan.group_id == group_id).all()
    results = []
    for b in bans:
        b_user = b.user
        results.append({
            "user_id": b.user_id,
            "username": b_user.username if b_user else "Unknown",
            "display_name": privacy.get_display_name(b_user) if b_user else "Unknown",
            "banned_at": b.created_at
        })

    return results
