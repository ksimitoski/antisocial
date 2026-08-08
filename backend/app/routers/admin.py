from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import models, schemas, auth, privacy

router = APIRouter(prefix="/api/admin", tags=["Admin"])

@router.get("/users")
def admin_list_users(
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(auth.get_current_admin)
):
    """
    List all platform users for management purposes (account state, confirmation, role).
    PRIVACY CONSTRAINT: Does NOT reveal user profiles or private data to admin.
    """
    users = db.query(models.User).order_by(models.User.id.asc()).all()
    user_list = []
    for u in users:
        effective_role = u.role if u.role else ("admin" if u.is_admin else "user")
        user_list.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": effective_role,
            "is_admin": u.is_admin or (effective_role == "admin"),
            "is_system_admin": u.is_system_admin,
            "is_confirmed": u.is_confirmed,
            "created_at": u.created_at
        })
    return user_list


@router.put("/users/{user_id}/role")
def admin_update_user_role(
    user_id: int,
    role_data: schemas.RoleUpdate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(auth.get_current_admin)
):
    """
    Assign user role: 'user', 'moderator', or 'admin'.
    """
    new_role = role_data.role.lower()
    if new_role not in ["user", "moderator", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'user', 'moderator', or 'admin'.")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_system_admin and new_role != "admin":
        raise HTTPException(status_code=400, detail="The initial system admin role cannot be changed.")

    if new_role != "admin" and (user.is_admin or user.role == "admin"):
        admin_count = db.query(models.User).filter((models.User.is_admin == True) | (models.User.role == "admin")).count()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the only administrator account.")

    user.role = new_role
    user.is_admin = (new_role == "admin")
    db.commit()
    db.refresh(user)

    return {"message": f"User {user.username} role updated to '{new_role}'.", "user_id": user.id, "role": new_role}


@router.get("/settings")
def get_site_settings(db: Session = Depends(get_db)):
    """
    Fetch public site settings (banner text, page welcome text, primary accent color, and site domain).
    """
    banner_setting = db.query(models.SiteSetting).filter(models.SiteSetting.key == "banner_text").first()
    page_text_setting = db.query(models.SiteSetting).filter(models.SiteSetting.key == "page_text").first()
    accent_color_setting = db.query(models.SiteSetting).filter(models.SiteSetting.key == "accent_color").first()
    site_domain_setting = db.query(models.SiteSetting).filter(models.SiteSetting.key == "site_domain").first()

    return {
        "banner_text": banner_setting.value if banner_setting else "",
        "page_text": page_text_setting.value if page_text_setting else "",
        "accent_color": accent_color_setting.value if accent_color_setting else "#dc2626",
        "site_domain": site_domain_setting.value if site_domain_setting else ""
    }


@router.put("/settings")
def update_site_settings(
    settings_data: schemas.SiteSettingUpdate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(auth.get_current_admin)
):
    """
    Update site settings (banner text, page text, accent color, and site domain). Admin only.
    """
    if settings_data.banner_text is not None:
        banner = db.query(models.SiteSetting).filter(models.SiteSetting.key == "banner_text").first()
        if not banner:
            banner = models.SiteSetting(key="banner_text", value=settings_data.banner_text)
            db.add(banner)
        else:
            banner.value = settings_data.banner_text

    if settings_data.page_text is not None:
        page_t = db.query(models.SiteSetting).filter(models.SiteSetting.key == "page_text").first()
        if not page_t:
            page_t = models.SiteSetting(key="page_text", value=settings_data.page_text)
            db.add(page_t)
        else:
            page_t.value = settings_data.page_text

    if settings_data.accent_color is not None:
        accent = db.query(models.SiteSetting).filter(models.SiteSetting.key == "accent_color").first()
        if not accent:
            accent = models.SiteSetting(key="accent_color", value=settings_data.accent_color.strip())
            db.add(accent)
        else:
            accent.value = settings_data.accent_color.strip()

    if settings_data.site_domain is not None:
        domain_setting = db.query(models.SiteSetting).filter(models.SiteSetting.key == "site_domain").first()
        domain_val = settings_data.site_domain.strip()
        if not domain_setting:
            domain_setting = models.SiteSetting(key="site_domain", value=domain_val)
            db.add(domain_setting)
        else:
            domain_setting.value = domain_val

    db.commit()
    return {"message": "Site settings updated successfully"}


@router.delete("/users/{user_id}")
def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(auth.get_current_admin)
):
    """
    Admin user removal trigger (cascades to delete all user records).
    """
    if user_id == admin_user.id:
        raise HTTPException(status_code=400, detail="Use the account settings page to delete your own account")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The initial system administrator account cannot be deleted."
        )

    username = user.username
    db.delete(user)
    db.commit()

    return {"message": f"User account {username} (ID: {user_id}) purged by administrator."}

