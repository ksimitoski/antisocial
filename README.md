# 🔥 Antisocial Platform

**Antisocial** is a modern, privacy-centric social network built with Python (FastAPI backend API + Flask web application frontend), SQLite database with cascade deletions, Docker containerization, and granular sharing controls.

---

## 🌟 Key Features

1. **Initial System Administrator Account**:
   - On the very first server startup, the backend automatically creates an initial system administrator (`admin` / `admin@antisocial.local`) with a randomly generated secure password.
   - The credentials are printed to the server console ONCE upon creation and never shown again.
   - The initial system admin account is permanently protected against deletion.

2. **Granular Privacy & Sharing Controls**:
   - Every profile field (Bio, Location, Birthdate, Phone) has custom visibility settings: `Public`, `Friends Only`, `Private`.
   - Every post can be shared with `Public`, `Friends Only`, `Groups`, or `Private (Only Me)`.

3. **Strict Admin Boundaries**:
   - Administrators can manage user accounts (activations, roles, deletion) but **cannot** view or alter private user profiles or unshared posts.

4. **Immediate Account Deletion**:
   - One-click account purge immediately deletes the user and cascades to remove all associated posts, media files, comments, likes, friendships, group memberships, and auth tokens.

5. **Friend Connections by Username or Email**:
   - Send friend requests easily from the Friends page by entering either a target `@username` or a registered `user@email.com` address.

6. **Image-Only Media Attachments**:
   - Post attachments support high-quality image formats (`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`). Video uploads are disallowed with clear, professional error validation.

7. **Comment Timestamps & Mobile Responsive Design**:
   - Post comments display ISO date/time timestamps positioned alongside deletion controls on desktop, and automatically adapt on mobile (`<=640px`) to display text above timestamps for readability.

8. **Conditional Landing & Public Feed**:
   - Unauthenticated visitors can explore the community's Public Feed directly from the index page without logging in. Logged-in users are presented with a clean welcome dashboard and feed navigation shortcut.

9. **Fluid & Reactive UI with Dark/Light Mode**:
   - Premium design featuring a **Crimson Red** theme (`#dc2626`), responsive glassmorphic navigation header, micro-animations, media preview uploads, and theme switching saved in `localStorage`.

---

## 🏗️ Architecture & Component Diagram

```mermaid
graph TD
    Client[Browser Client - Web Page UI]
    
    subgraph Frontend Container (Flask Service - Port 5000)
        Flask[Flask Gateway App]
        Jinja[Jinja2 HTML5 Templates]
        CSS[Crimson Red CSS Design System]
        JS[Reactive UI JS / Media Handler]
    end

    subgraph Backend Container (FastAPI Service - Port 8000)
        FastAPI[FastAPI REST Engine]
        Auth[JWT & Auth System]
        PrivacyEngine[Privacy & Visibility Evaluator]
        Uploads[Media Storage Handler]
        AdminModule[Admin User Manager]
    end

    subgraph Database Layer (Volume Mounted)
        SQLite[(SQLite DB - antisocial.db)]
    end

    Client -->|HTTP Requests| Flask
    Flask -->|Proxies / REST API| FastAPI
    FastAPI -->|Token & Session Auth| Auth
    FastAPI -->|Evaluates Permissions| PrivacyEngine
    FastAPI -->|Reads/Writes Data| SQLite
    FastAPI -->|Stores Uploads| Uploads
    AdminModule -->|Account Actions ONLY| SQLite
    PrivacyEngine -. Blocks Admin Profile Access .- SQLite
```

---

## 🚀 Getting Started with Docker Compose

### Prerequisites
- Docker (version 20.10+)
- Docker Compose (version 2.0+)

### 1. Environment Setup
Copy or inspect `.env` in the root directory:
```bash
cp .env.example .env
```

Configuration variables inside `.env`:
```ini
SECRET_KEY=antisocial_super_secret_jwt_and_session_key_2026_red
DATABASE_URL=sqlite:////app/data/antisocial.db
BACKEND_PORT=8000
FRONTEND_PORT=5000
BACKEND_INTERNAL_URL=http://backend:8000
MAX_UPLOAD_SIZE_MB=50
```

### 2. Launch Services
Run the following command from the root project directory:
```bash
docker-compose up --build
```

Access the platform in your browser:
- **Flask Frontend**: [http://localhost:5000](http://localhost:5000)
- **FastAPI API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧪 Running Automated Tests

To execute the full test suite (privacy rules, friend requests by email/username, image upload validation, account deletion cascading):
```bash
cd backend
pip install -r requirements.txt
pytest
```
