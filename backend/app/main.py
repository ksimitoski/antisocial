import os
import secrets
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import engine, Base, SessionLocal, run_db_migrations, get_db
from app import models, auth, privacy
from app.routers import auth as auth_router, users, posts, groups, admin, messages, notifications

# Initialize database tables & run column migrations
Base.metadata.create_all(bind=engine)
run_db_migrations(engine)


import sys

def init_system_admin(db_session=None):
    close_db = False
    if db_session is None:
        db = SessionLocal()
        close_db = True
    else:
        db = db_session

    try:
        system_admin = db.query(models.User).filter(models.User.is_system_admin == True).first()
        if not system_admin:
            # Check if an 'admin' user already exists from a previous run
            existing_admin = db.query(models.User).filter(models.User.username == "admin").first()
            raw_password = secrets.token_urlsafe(12)
            hashed_pw = auth.get_password_hash(raw_password)

            if existing_admin:
                admin_user = existing_admin
                admin_user.hashed_password = hashed_pw
                admin_user.is_admin = True
                admin_user.is_system_admin = True
                admin_user.is_confirmed = True
            else:
                admin_user = models.User(
                    username="admin",
                    email="admin@antisocial.local",
                    hashed_password=hashed_pw,
                    is_admin=True,
                    is_system_admin=True,
                    is_confirmed=True
                )
                db.add(admin_user)
                db.commit()
                db.refresh(admin_user)

                profile = models.UserProfile(
                    user_id=admin_user.id,
                    bio="Initial System Administrator",
                    bio_visibility="public"
                )
                db.add(profile)

            db.commit()

            msg = f"""
====================================================================
 🔥 ANTISOCIAL PLATFORM - INITIAL SYSTEM ADMIN CREATED
-------------------------------------------------------------------
 Username: {admin_user.username}
 Email:    {admin_user.email}
 Password: {raw_password}
-------------------------------------------------------------------
 Save this password! It will NEVER be printed again.
====================================================================
"""
            print(msg, flush=True)
            sys.stdout.flush()
    finally:
        if close_db:
            db.close()



@asynccontextmanager
async def lifespan(app: FastAPI):
    init_system_admin()
    yield

app = FastAPI(
    title="Antisocial API",
    description="Privacy-focused social platform API",
    version="1.0.0",
    lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline' fonts.googleapis.com; "
        "font-src 'self' fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "frame-ancestors 'none';"
    )
    return response

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
@app.get("/uploads/{filename}")
def serve_upload_file(
    filename: str,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional)
):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Media file not found")

    # Check if this media file belongs to a post
    post = db.query(models.Post).filter(
        (models.Post.media_url == f"/uploads/{filename}") |
        (models.Post.media_url == filename)
    ).first()

    if post:
        viewer_id = current_user.id if current_user else None
        # Enforce strict post privacy check on media files!
        # Unauthenticated users or users without view rights are denied access (403 Forbidden).
        if not privacy.can_view_post(db, viewer_id, post):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to this media file is restricted by post privacy settings"
            )

    return FileResponse(file_path)


app.include_router(auth_router.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(groups.router)
app.include_router(admin.router)
app.include_router(messages.router)
app.include_router(notifications.router)


# Automated background worker thread for email notification digests
def start_automated_email_digest_worker():
    import threading
    import time

    def worker():
        # Allow database initialization on boot
        time.sleep(2)
        while True:
            try:
                db = SessionLocal()
                notifications.process_email_notification_digests(db)
                db.close()
            except Exception:
                pass
            time.sleep(20)  # Consistently run automated email digest check every 20 seconds

    thread = threading.Thread(target=worker, daemon=True, name="AutomatedEmailDigestThread")
    thread.start()

start_automated_email_digest_worker()


@app.get("/")
def root():
    return {
        "name": "Antisocial API",
        "status": "online",
        "documentation": "/docs"
    }
