import datetime
import os
from fastapi import APIRouter, Depends, HTTPException, status, Header, Response, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth, email, security_utils
router = APIRouter(prefix="/api/auth", tags=["Auth"])


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
        if client_ip:
            return client_ip
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    return request.client.host if request.client else "127.0.0.1"


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(user_data: schemas.UserRegister, response: Response, db: Session = Depends(get_db)):
    # Check if username or email already exists
    existing_user = db.query(models.User).filter(
        (models.User.username == user_data.username) | (models.User.email == user_data.email)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or Email already registered"
        )

    hashed_pw = auth.get_password_hash(user_data.password)
    user = models.User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_pw,
        is_admin=False,
        is_system_admin=False,
        is_confirmed=False
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Create empty user profile
    profile = models.UserProfile(
        user_id=user.id,
        bio="Hello! I am using Antisocial.",
        bio_visibility="public",
        location_visibility="public",
        birthdate_visibility="private",
        phone_visibility="private"
    )
    db.add(profile)
    db.commit()

    # Generate email confirmation token
    token_str = auth.generate_email_token()
    expires = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    email_token = models.EmailToken(
        user_id=user.id,
        token=token_str,
        expires_at=expires
    )
    db.add(email_token)
    db.commit()

    confirm_url = f"/confirm-email?token={token_str}"

    # Send confirmation email via SMTP
    email_sent = email.send_confirmation_email(user.email, user.username, token_str, db=db)

    response.headers["X-Confirmation-Token"] = token_str
    response.headers["X-Confirmation-Url"] = confirm_url

    return {
        "message": "User registered successfully. Please check your inbox and confirm your email address to log in.",
        "user_id": user.id,
        "is_confirmed": user.is_confirmed,
        "email_sent": email_sent,
        "confirmation_url": confirm_url,
        "token": token_str
    }


@router.get("/confirm")
def confirm_email(token: str, db: Session = Depends(get_db)):
    token_record = db.query(models.EmailToken).filter(models.EmailToken.token == token).first()
    if not token_record:
        raise HTTPException(status_code=400, detail="Invalid confirmation token")

    if token_record.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="Confirmation token has expired")

    user = token_record.user
    user.is_confirmed = True
    db.delete(token_record)
    db.commit()

    return {"message": "Email confirmed successfully. You can now log in."}


@router.post("/login", response_model=schemas.Token)
def login(credentials: schemas.UserLogin, request: Request, db: Session = Depends(get_db)):
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "Unknown")[:250]

    user = db.query(models.User).filter(
        (models.User.username == credentials.username_or_email) |
        (models.User.email == credentials.username_or_email)
    ).first()

    if not user or not auth.verify_password(credentials.password, user.hashed_password):
        if user:
            log_entry = models.SecurityLog(
                user_id=user.id,
                event_type="login_failed",
                ip_address=client_ip,
                user_agent=user_agent,
                details="Invalid password attempt"
            )
            db.add(log_entry)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password"
        )

    if not user.is_confirmed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address not confirmed yet. Please verify your email."
        )

    # 2FA Enforcement
    if user.is_totp_enabled:
        if not credentials.totp_code or not credentials.totp_code.strip():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Two-factor authentication code required. Please enter your 6-digit authenticator code or recovery code."
            )
        
        valid_totp = security_utils.verify_totp_code(user.totp_secret, credentials.totp_code)
        valid_backup = False
        if not valid_totp and user.totp_backup_codes:
            valid_backup, new_backup_str = security_utils.verify_and_consume_backup_code(user.totp_backup_codes, credentials.totp_code)
            if valid_backup:
                user.totp_backup_codes = new_backup_str
                db.commit()

        if not valid_totp and not valid_backup:
            log_entry = models.SecurityLog(
                user_id=user.id,
                event_type="2fa_failed",
                ip_address=client_ip,
                user_agent=user_agent,
                details="Invalid 2FA code attempt"
            )
            db.add(log_entry)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid 2FA code or backup recovery code"
            )

    expires_delta = datetime.timedelta(days=3650) if credentials.remember_me else None
    token_str = auth.create_access_token(data={"sub": user.id}, expires_delta=expires_delta)

    # Track active session
    existing_session = db.query(models.UserSession).filter(models.UserSession.session_token == token_str).first()
    if existing_session:
        existing_session.last_active_at = datetime.datetime.utcnow()
    else:
        new_session = models.UserSession(
            user_id=user.id,
            session_token=token_str,
            ip_address=client_ip,
            user_agent=user_agent
        )
        db.add(new_session)

    # Check if login is from a new IP
    previous_login = db.query(models.SecurityLog).filter(
        models.SecurityLog.user_id == user.id,
        models.SecurityLog.event_type.in_(["login", "login_new_ip"]),
        models.SecurityLog.ip_address == client_ip
    ).first()

    event_type = "login"
    if not previous_login:
        event_type = "login_new_ip"
        email.send_security_alert_email(user.email, user.username, client_ip, user_agent, event_desc="New Login from Unrecognized IP", db=db)

    log_entry = models.SecurityLog(
        user_id=user.id,
        event_type=event_type,
        ip_address=client_ip,
        user_agent=user_agent
    )
    db.add(log_entry)
    db.commit()

    effective_role = user.role if user.role else ("admin" if user.is_admin else "user")
    return {
        "access_token": token_str,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "role": effective_role,
        "is_admin": user.is_admin or (effective_role == "admin"),
        "is_confirmed": user.is_confirmed,
        "is_totp_enabled": user.is_totp_enabled
    }


# -------------------------------------------------------------
# 2FA Management Endpoints
# -------------------------------------------------------------

@router.post("/2fa/setup")
def setup_2fa(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Generate temporary TOTP secret for 2FA onboarding."""
    secret = security_utils.generate_totp_secret()
    current_user.totp_secret = secret
    db.commit()

    totp_uri = f"otpauth://totp/Antisocial:{current_user.username}?secret={secret}&issuer=Antisocial"
    return {
        "secret": secret,
        "otpauth_url": totp_uri
    }


@router.post("/2fa/enable")
def enable_2fa(req: schemas.TOTPVerifyRequest, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Verify code against secret and activate 2FA."""
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="Please initiate 2FA setup first.")

    if not security_utils.verify_totp_code(current_user.totp_secret, req.code):
        raise HTTPException(status_code=400, detail="Invalid 2FA verification code. Please check your authenticator app and try again.")

    backup_codes, hashed_codes = security_utils.generate_backup_codes()
    current_user.is_totp_enabled = True
    current_user.totp_backup_codes = hashed_codes
    db.commit()

    return {
        "message": "Two-factor authentication successfully enabled!",
        "backup_codes": backup_codes
    }


@router.post("/2fa/disable")
def disable_2fa(req: schemas.TOTPVerifyRequest, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Disable 2FA after verifying code or password."""
    valid_totp = security_utils.verify_totp_code(current_user.totp_secret, req.code)
    valid_pass = auth.verify_password(req.code, current_user.hashed_password)

    if not valid_totp and not valid_pass:
        raise HTTPException(status_code=400, detail="Invalid 2FA code or password.")

    current_user.is_totp_enabled = False
    current_user.totp_secret = None
    current_user.totp_backup_codes = None
    db.commit()

    return {"message": "Two-factor authentication disabled successfully."}


# -------------------------------------------------------------
# Active Session Management Endpoints
# -------------------------------------------------------------

@router.get("/sessions")
def list_active_sessions(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    sessions = db.query(models.UserSession).filter(models.UserSession.user_id == current_user.id).order_by(models.UserSession.last_active_at.desc()).all()
    return [
        {
            "id": s.id,
            "ip_address": s.ip_address or "Unknown",
            "user_agent": s.user_agent or "Unknown Browser",
            "last_active_at": s.last_active_at,
            "created_at": s.created_at
        } for s in sessions
    ]


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    sess = db.query(models.UserSession).filter(models.UserSession.id == session_id, models.UserSession.user_id == current_user.id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(sess)
    db.commit()
    return {"message": "Session revoked successfully"}


@router.delete("/sessions/revoke-others")
def revoke_other_sessions(token: str = Depends(auth.oauth2_scheme), current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    db.query(models.UserSession).filter(
        models.UserSession.user_id == current_user.id,
        models.UserSession.session_token != token
    ).delete()
    db.commit()
    return {"message": "All other sessions have been logged out."}


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@router.post("/forgot-password")
def request_password_reset(req: schemas.PasswordResetRequest, response: Response, db: Session = Depends(get_db)):
    import secrets
    import string

    user = db.query(models.User).filter(models.User.email == req.email).first()
    if not user:
        # Don't reveal user existence
        return {"message": "If an account with that email exists, a password reset email has been sent."}

    # Remove existing reset tokens for this user
    db.query(models.PasswordResetToken).filter(models.PasswordResetToken.user_id == user.id).delete()
    db.commit()

    token_str = auth.generate_email_token()
    code = ''.join(secrets.choice(string.digits) for _ in range(6))
    expires = datetime.datetime.utcnow() + datetime.timedelta(hours=1)

    reset_token = models.PasswordResetToken(
        user_id=user.id,
        token=token_str,
        code=code,
        expires_at=expires
    )
    db.add(reset_token)
    db.commit()

    email_sent = email.send_password_reset_email(user.email, user.username, code, token_str, db=db)

    response.headers["X-Reset-Token"] = token_str
    response.headers["X-Reset-Code"] = code

    return {
        "message": "Password reset instructions sent. Please check your email for the confirmation code or link.",
        "email_sent": email_sent,
        "token": token_str,
        "code": code
    }


@router.post("/verify-reset-code")
def verify_reset_code(req: schemas.PasswordResetVerifyCode, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == req.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid email or confirmation code")

    token_record = db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.user_id == user.id,
        models.PasswordResetToken.code == req.code.strip()
    ).first()

    if not token_record:
        raise HTTPException(status_code=400, detail="Invalid confirmation code")

    if token_record.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="Confirmation code has expired")

    return {
        "message": "Confirmation code verified successfully.",
        "token": token_record.token
    }


@router.post("/reset-password")
def reset_password(req: schemas.PasswordResetConfirm, db: Session = Depends(get_db)):
    if req.password != req.password_confirm:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    if len(req.password.strip()) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters long")

    token_record = None
    if req.token:
        token_record = db.query(models.PasswordResetToken).filter(models.PasswordResetToken.token == req.token).first()
    elif req.email and req.code:
        user = db.query(models.User).filter(models.User.email == req.email).first()
        if user:
            token_record = db.query(models.PasswordResetToken).filter(
                models.PasswordResetToken.user_id == user.id,
                models.PasswordResetToken.code == req.code.strip()
            ).first()

    if not token_record:
        raise HTTPException(status_code=400, detail="Invalid or missing reset token / confirmation code")

    if token_record.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="Reset token or confirmation code has expired")

    user = token_record.user
    user.hashed_password = auth.get_password_hash(req.password)
    user.is_confirmed = True  # Automatically mark confirmed upon reset

    db.delete(token_record)
    db.commit()

    return {"message": "Password updated successfully! You can now log in with your new password."}

