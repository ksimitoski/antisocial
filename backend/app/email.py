import os
import smtplib
import logging
from typing import Optional
from sqlalchemy.orm import Session
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

SMTP_ENABLED = os.getenv("SMTP_ENABLED", "true").lower() in ("true", "1", "yes")
SMTP_SERVER = os.getenv("SMTP_SERVER", "192.168.2.3")
SMTP_PORT = int(os.getenv("SMTP_PORT", "25"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@antisocial.local")
FRONTEND_URL = os.getenv("FRONTEND_PUBLIC_URL", os.getenv("FRONTEND_URL", "http://localhost:5000")).rstrip("/")


def get_frontend_url(db: Optional[Session] = None) -> str:
    """Fetch configured site domain from DB or fallback to environment FRONTEND_URL."""
    from app import models
    from app.database import SessionLocal

    domain_val = None
    if db is not None:
        try:
            setting = db.query(models.SiteSetting).filter(models.SiteSetting.key == "site_domain").first()
            if setting and setting.value and setting.value.strip():
                domain_val = setting.value.strip()
        except Exception as e:
            logger.warning(f"Failed to query site_domain from db: {e}")
    else:
        try:
            temp_db = SessionLocal()
            try:
                setting = temp_db.query(models.SiteSetting).filter(models.SiteSetting.key == "site_domain").first()
                if setting and setting.value and setting.value.strip():
                    domain_val = setting.value.strip()
            finally:
                temp_db.close()
        except Exception as e:
            logger.warning(f"Failed to query site_domain with temp db session: {e}")

    if domain_val:
        if not (domain_val.startswith("http://") or domain_val.startswith("https://")):
            domain_val = f"http://{domain_val}"
        return domain_val.rstrip("/")

    return FRONTEND_URL


def send_confirmation_email(user_email: str, username: str, token: str, db: Optional[Session] = None) -> bool:
    frontend_url = get_frontend_url(db)
    full_url = f"{frontend_url}/confirm-email?token={token}"

    logger.info(f"Preparing verification email for {user_email} (Username: {username})")

    if not SMTP_ENABLED:
        logger.info(f"[SMTP Disabled] Confirmation link for {user_email}: {full_url}")
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Verify Your Antisocial Account"
    msg["From"] = f"Antisocial Platform <{FROM_EMAIL}>"
    msg["To"] = user_email

    text_content = f"""Hello {username},

Thank you for registering on Antisocial!

Please confirm your account by visiting the following link:
{full_url}

This verification link will expire in 24 hours. If you did not create an account on Antisocial, please ignore this message.

-- 
Antisocial Platform
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Confirm Your Account</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #0f172a; padding: 40px 10px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" max-width="600" cellspacing="0" cellpadding="0" border="0" style="max-width: 600px; background-color: #1e293b; border-radius: 12px; overflow: hidden; border: 1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
          <!-- Header -->
          <tr>
            <td style="background-color: #dc2626; padding: 25px 30px; text-align: center;">
              <h1 style="margin: 0; color: #ffffff; font-size: 26px; font-weight: 800; letter-spacing: -0.5px;">🔥 Antisocial</h1>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding: 35px 30px;">
              <h2 style="margin-top: 0; margin-bottom: 16px; color: #ffffff; font-size: 20px; font-weight: 600;">Welcome, {username}!</h2>
              <p style="margin-bottom: 20px; color: #cbd5e1; font-size: 15px; line-height: 1.6;">
                Thank you for joining Antisocial, the privacy-first social platform. Please verify your email address to complete your registration and activate your account.
              </p>
              
              <!-- CTA Button -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin: 28px 0;">
                <tr>
                  <td align="center" style="border-radius: 8px; background-color: #dc2626;">
                    <a href="{full_url}" target="_blank" style="font-size: 16px; font-family: sans-serif; color: #ffffff; text-decoration: none; border-radius: 8px; padding: 14px 32px; border: 1px solid #dc2626; display: inline-block; font-weight: 700;">
                      Verify Email Address
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin-bottom: 12px; color: #94a3b8; font-size: 13px; line-height: 1.5;">
                If the button above doesn't work, copy and paste the link below into your web browser:
              </p>
              <p style="margin-bottom: 24px; word-break: break-all; font-size: 13px; line-height: 1.4;">
                <a href="{full_url}" style="color: #f87171; text-decoration: underline;">{full_url}</a>
              </p>
              
              <div style="border-top: 1px dashed #334155; padding-top: 20px; margin-top: 24px;">
                <p style="margin: 0; color: #64748b; font-size: 12px; line-height: 1.5;">
                  ⏱️ This link will expire in 24 hours.<br>
                  🔒 If you did not sign up for an Antisocial account, no action is required and you can safely ignore this email.
                </p>
              </div>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background-color: #0f172a; padding: 20px 30px; text-align: center; border-top: 1px solid #1e293b;">
              <p style="margin: 0; color: #64748b; font-size: 12px;">
                &copy; Antisocial Platform &bull; Privacy-First Social Media
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    part1 = MIMEText(text_content, "plain")
    part2 = MIMEText(html_content, "html")
    msg.attach(part1)
    msg.attach(part2)

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=5) as server:
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=5) as server:
                if SMTP_PORT == 587:
                    try:
                        server.starttls()
                    except Exception as tls_err:
                        logger.warning(f"STARTTLS failed or unsupported: {tls_err}")
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)

        logger.info(f"Confirmation email successfully sent via SMTP ({SMTP_SERVER}:{SMTP_PORT}) to {user_email}")
        return True
    except Exception as e:
        logger.error(f"SMTP error sending confirmation email to {user_email} via {SMTP_SERVER}:{SMTP_PORT}: {e}")
        return False


def send_password_reset_email(user_email: str, username: str, code: str, token: str, db: Optional[Session] = None) -> bool:
    frontend_url = get_frontend_url(db)
    full_url = f"{frontend_url}/reset-password?token={token}"

    logger.info(f"Preparing password reset email for {user_email} (Code: {code})")

    if not SMTP_ENABLED:
        logger.info(f"[SMTP Disabled] Password Reset link for {user_email}: {full_url} (Code: {code})")
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset Your Antisocial Password"
    msg["From"] = f"Antisocial Platform <{FROM_EMAIL}>"
    msg["To"] = user_email

    text_content = f"""Hello {username},

You requested to reset your password on Antisocial.

Your confirmation code is: {code}

Alternatively, you can reset your password directly by visiting the following link:
{full_url}

This password reset code/link will expire in 1 hour. If you did not request a password reset, please ignore this email.

-- 
Antisocial Platform
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reset Your Password</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #0f172a; padding: 40px 10px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" max-width="600" cellspacing="0" cellpadding="0" border="0" style="max-width: 600px; background-color: #1e293b; border-radius: 12px; overflow: hidden; border: 1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
          <!-- Header -->
          <tr>
            <td style="background-color: #dc2626; padding: 25px 30px; text-align: center;">
              <h1 style="margin: 0; color: #ffffff; font-size: 26px; font-weight: 800; letter-spacing: -0.5px;">🔥 Antisocial</h1>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding: 35px 30px;">
              <h2 style="margin-top: 0; margin-bottom: 16px; color: #ffffff; font-size: 20px; font-weight: 600;">Password Reset Request</h2>
              <p style="margin-bottom: 20px; color: #cbd5e1; font-size: 15px; line-height: 1.6;">
                Hello <strong>{username}</strong>, we received a request to reset your password for your Antisocial account.
              </p>
              
              <div style="background-color: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 20px; text-align: center; margin: 24px 0;">
                <span style="font-size: 14px; color: #94a3b8; display: block; margin-bottom: 8px;">Your Confirmation Code:</span>
                <span style="font-size: 32px; font-weight: 800; color: #dc2626; letter-spacing: 6px; font-family: monospace;">{code}</span>
              </div>

              <!-- CTA Button -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin: 28px 0;">
                <tr>
                  <td align="center" style="border-radius: 8px; background-color: #dc2626;">
                    <a href="{full_url}" target="_blank" style="font-size: 16px; font-family: sans-serif; color: #ffffff; text-decoration: none; border-radius: 8px; padding: 14px 32px; border: 1px solid #dc2626; display: inline-block; font-weight: 700;">
                      Reset Password Directly
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin-bottom: 12px; color: #94a3b8; font-size: 13px; line-height: 1.5;">
                Or copy and paste this link into your browser:
              </p>
              <p style="margin-bottom: 24px; word-break: break-all; font-size: 13px; line-height: 1.4;">
                <a href="{full_url}" style="color: #f87171; text-decoration: underline;">{full_url}</a>
              </p>
              
              <div style="border-top: 1px dashed #334155; padding-top: 20px; margin-top: 24px;">
                <p style="margin: 0; color: #64748b; font-size: 12px; line-height: 1.5;">
                  ⏱️ This code and link will expire in 1 hour.<br>
                  🔒 If you did not request a password reset, you can safely ignore this email.
                </p>
              </div>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background-color: #0f172a; padding: 20px 30px; text-align: center; border-top: 1px solid #1e293b;">
              <p style="margin: 0; color: #64748b; font-size: 12px;">
                &copy; Antisocial Platform &bull; Privacy-First Social Media
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    part1 = MIMEText(text_content, "plain")
    part2 = MIMEText(html_content, "html")
    msg.attach(part1)
    msg.attach(part2)

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=5) as server:
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=5) as server:
                if SMTP_PORT == 587:
                    try:
                        server.starttls()
                    except Exception as tls_err:
                        logger.warning(f"STARTTLS failed or unsupported: {tls_err}")
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)

        logger.info(f"Password reset email successfully sent via SMTP ({SMTP_SERVER}:{SMTP_PORT}) to {user_email}")
        return True
    except Exception as e:
        logger.error(f"SMTP error sending password reset email to {user_email} via {SMTP_SERVER}:{SMTP_PORT}: {e}")
        return False


def send_batch_digest_email(user_email: str, username: str, messages: list, comments: list, posts: Optional[list] = None, obscure: bool = False, db: Optional[Session] = None) -> bool:
    posts = posts or []
    total = len(messages) + len(comments) + len(posts)
    if total == 0:
        return True

    logger.info(f"Preparing batch email notification digest for {user_email} ({len(messages)} messages, {len(comments)} comments, {len(posts)} posts)")

    frontend_url = get_frontend_url(db)
    full_url = f"{frontend_url}/feed"

    if not SMTP_ENABLED:
        logger.info(f"[SMTP Disabled] Batch notification digest email for {user_email}: {total} items")
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔥 Antisocial Activity Digest ({total} new update{'s' if total > 1 else ''})"
    msg["From"] = f"Antisocial Platform <{FROM_EMAIL}>"
    msg["To"] = user_email

    # Plain text content
    text_lines = [
        f"Hello {username},",
        "",
        "Here is your batch activity digest with recent updates on Antisocial:",
        ""
    ]

    if messages:
        text_lines.append(f"💬 Direct Messages ({len(messages)}):")
        for m in messages:
            sender_name = m.get("sender_display_name") or m.get("sender_username", "User")
            snippet = "New message received (content hidden for privacy)" if obscure else (m.get("content") or "Sent a message")
            text_lines.append(f"  • {sender_name}: {snippet}")
        text_lines.append("")

    if comments:
        text_lines.append(f"💬 Comments on Your Posts ({len(comments)}):")
        for c in comments:
            author_name = c.get("author_display_name") or c.get("author_username", "User")
            snippet = "New comment received (content hidden for privacy)" if obscure else (c.get("content") or "")
            post_id = c.get("post_id")
            post_link_str = f" -> View Post: {frontend_url}/post/{post_id}" if post_id else ""
            text_lines.append(f"  • {author_name}: {snippet}{post_link_str}")
        text_lines.append("")

    if posts:
        text_lines.append(f"📌 Posts from Friends You Follow ({len(posts)}):")
        for p in posts:
            author_name = p.get("author_display_name") or p.get("author_username", "User")
            snippet = "New post (content hidden for privacy)" if obscure else (p.get("content") or "")
            post_id = p.get("id")
            post_link_str = f" -> View Post: {frontend_url}/post/{post_id}" if post_id else ""
            text_lines.append(f"  • {author_name}: {snippet}{post_link_str}")
        text_lines.append("")

    text_lines.extend([
        f"View your updates: {full_url}",
        "",
        "-- ",
        "Antisocial Platform"
    ])
    text_content = "\n".join(text_lines)

    # HTML content
    msg_html_items = ""
    if messages:
        msg_html_items += f'<h3 style="color: #f87171; font-size: 16px; margin-top: 20px; margin-bottom: 10px;">💬 Direct Messages ({len(messages)})</h3><ul style="padding-left: 20px; color: #cbd5e1; font-size: 14px; margin-bottom: 20px;">'
        for m in messages:
            sender_name = m.get("sender_display_name") or m.get("sender_username", "User")
            snippet = "New message received (content hidden for privacy)" if obscure else (m.get("content") or "Sent a message")
            if len(snippet) > 80 and not obscure:
                snippet = snippet[:77] + "..."
            msg_html_items += f'<li style="margin-bottom: 6px;"><strong style="color: #ffffff;">{sender_name}:</strong> {snippet}</li>'
        msg_html_items += '</ul>'

    cmt_html_items = ""
    if comments:
        cmt_html_items += f'<h3 style="color: #f87171; font-size: 16px; margin-top: 20px; margin-bottom: 10px;">💬 Comments on Your Posts ({len(comments)})</h3><ul style="padding-left: 20px; color: #cbd5e1; font-size: 14px; margin-bottom: 20px;">'
        for c in comments:
            author_name = c.get("author_display_name") or c.get("author_username", "User")
            snippet = "New comment received (content hidden for privacy)" if obscure else (c.get("content") or "")
            if len(snippet) > 80 and not obscure:
                snippet = snippet[:77] + "..."
            post_id = c.get("post_id")
            post_link_html = f' &nbsp;<a href="{frontend_url}/post/{post_id}" target="_blank" style="color: #f87171; text-decoration: underline; font-size: 13px; font-weight: 600;">🔗 View Post</a>' if post_id else ""
            cmt_html_items += f'<li style="margin-bottom: 10px;"><strong style="color: #ffffff;">{author_name}:</strong> "{snippet}"{post_link_html}</li>'
        cmt_html_items += '</ul>'

    pst_html_items = ""
    if posts:
        pst_html_items += f'<h3 style="color: #f87171; font-size: 16px; margin-top: 20px; margin-bottom: 10px;">📌 Posts from Friends You Follow ({len(posts)})</h3><ul style="padding-left: 20px; color: #cbd5e1; font-size: 14px; margin-bottom: 20px;">'
        for p in posts:
            author_name = p.get("author_display_name") or p.get("author_username", "User")
            snippet = "New post (content hidden for privacy)" if obscure else (p.get("content") or "")
            if len(snippet) > 80 and not obscure:
                snippet = snippet[:77] + "..."
            post_id = p.get("id")
            post_link_html = f' &nbsp;<a href="{frontend_url}/post/{post_id}" target="_blank" style="color: #f87171; text-decoration: underline; font-size: 13px; font-weight: 600;">🔗 View Post</a>' if post_id else ""
            pst_html_items += f'<li style="margin-bottom: 10px;"><strong style="color: #ffffff;">{author_name}:</strong> "{snippet}"{post_link_html}</li>'
        pst_html_items += '</ul>'

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Antisocial Activity Digest</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #0f172a; padding: 40px 10px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" max-width="600" cellspacing="0" cellpadding="0" border="0" style="max-width: 600px; background-color: #1e293b; border-radius: 12px; overflow: hidden; border: 1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
          <!-- Header -->
          <tr>
            <td style="background-color: #dc2626; padding: 25px 30px; text-align: center;">
              <h1 style="margin: 0; color: #ffffff; font-size: 26px; font-weight: 800; letter-spacing: -0.5px;">🔥 Antisocial</h1>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding: 35px 30px;">
              <h2 style="margin-top: 0; margin-bottom: 16px; color: #ffffff; font-size: 20px; font-weight: 600;">Hello {username}!</h2>
              <p style="margin-bottom: 20px; color: #cbd5e1; font-size: 15px; line-height: 1.6;">
                Here is your batch activity digest summarizing recent updates on Antisocial:
              </p>
              
              <div style="background-color: #0f172a; border-radius: 8px; padding: 15px 20px; border: 1px solid #334155; margin-bottom: 24px;">
                {msg_html_items}
                {cmt_html_items}
                {pst_html_items}
              </div>

              <!-- CTA Button -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin: 28px 0;">
                <tr>
                  <td align="center" style="border-radius: 8px; background-color: #dc2626;">
                    <a href="{full_url}" target="_blank" style="font-size: 16px; font-family: sans-serif; color: #ffffff; text-decoration: none; border-radius: 8px; padding: 14px 32px; border: 1px solid #dc2626; display: inline-block; font-weight: 700;">
                      View Activity on Antisocial
                    </a>
                  </td>
                </tr>
              </table>

              <div style="border-top: 1px dashed #334155; padding-top: 20px; margin-top: 24px;">
                <p style="margin: 0; color: #64748b; font-size: 12px; line-height: 1.5;">
                  📦 You are receiving this batch notification digest based on your email notification preferences.<br>
                  ⚙️ You can adjust or turn off email digests anytime in your Antisocial Account Settings.
                </p>
              </div>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background-color: #0f172a; padding: 20px 30px; text-align: center; border-top: 1px solid #1e293b;">
              <p style="margin: 0; color: #64748b; font-size: 12px;">
                &copy; Antisocial Platform &bull; Privacy-First Social Media
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    part1 = MIMEText(text_content, "plain")
    part2 = MIMEText(html_content, "html")
    msg.attach(part1)
    msg.attach(part2)

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=5) as server:
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=5) as server:
                if SMTP_PORT == 587:
                    try:
                        server.starttls()
                    except Exception as tls_err:
                        logger.warning(f"STARTTLS failed or unsupported: {tls_err}")
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)

        logger.info(f"Batch email digest successfully sent to {user_email}")
        return True
    except Exception as e:
        logger.error(f"SMTP error sending batch email digest to {user_email}: {e}")
        return False


def send_security_alert_email(user_email: str, username: str, ip_address: str, user_agent: str, event_desc: str = "New Login Detected", db: Optional[Session] = None) -> bool:
    """Send security alert email for new IP logins or sensitive security events."""
    if not SMTP_ENABLED:
        logger.info(f"[SMTP Disabled] Security alert email skipped for {user_email}")
        return False

    base_url = get_frontend_url(db)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔒 Security Alert: {event_desc} on Antisocial"
    msg["From"] = FROM_EMAIL
    msg["To"] = user_email

    text_content = f"""
Hello {username},

Security Alert: {event_desc}

We detected activity on your Antisocial account:
- Event: {event_desc}
- IP Address: {ip_address}
- Device / Browser: {user_agent}

If this was you, no action is required.
If you did NOT perform this activity, please log in immediately and revoke active sessions:
{base_url}/settings

Antisocial Security Team
"""

    html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
</head>
<body style="font-family: Arial, sans-serif; background-color: #0b0f19; color: #f1f5f9; padding: 20px;">
  <div style="max-width: 600px; margin: 0 auto; background: #151d2a; border-radius: 8px; border: 1px solid #232e42; overflow: hidden;">
    <div style="background: #dc2626; padding: 20px; text-align: center; color: white;">
      <h2 style="margin: 0;">🔒 Security Alert</h2>
    </div>
    <div style="padding: 24px; color: #f1f5f9;">
      <p>Hello <strong>{username}</strong>,</p>
      <p style="font-size: 15px;">We detected a new login or security event on your Antisocial account:</p>
      <div style="background: #1e293b; padding: 16px; border-radius: 6px; margin: 16px 0; font-size: 14px;">
        <p style="margin: 4px 0;"><strong>Event:</strong> {event_desc}</p>
        <p style="margin: 4px 0;"><strong>IP Address:</strong> {ip_address}</p>
        <p style="margin: 4px 0;"><strong>Device/Browser:</strong> {user_agent}</p>
      </div>
      <p style="color: #94a3b8; font-size: 13px;">If this was you, you can safely ignore this message. If you did NOT initiate this login, please change your password and manage active sessions immediately.</p>
      <div style="text-align: center; margin-top: 24px;">
        <a href="{base_url}/settings" style="background: #dc2626; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Manage Account Security</a>
      </div>
    </div>
  </div>
</body>
</html>
"""

    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=5) as server:
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=5) as server:
                if SMTP_PORT == 587:
                    try:
                        server.starttls()
                    except Exception:
                        pass
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"Failed to send security alert email to {user_email}: {e}")
        return False


