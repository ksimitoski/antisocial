import io
import os
import hmac
import time
import struct
import base64
import hashlib
import secrets
from PIL import Image
from typing import Optional, List, Tuple

def strip_exif_data(contents: bytes, ext: str) -> bytes:
    """Strips EXIF metadata (GPS location, camera details, timestamps) from image bytes."""
    try:
        image = Image.open(io.BytesIO(contents))
        # Create a new image without metadata headers
        data = list(image.getdata())
        clean_img = Image.new(image.mode, image.size)
        clean_img.putdata(data)

        out = io.BytesIO()
        ext_lower = ext.lower()
        if ext_lower in [".jpg", ".jpeg"]:
            fmt = "JPEG"
        elif ext_lower == ".png":
            fmt = "PNG"
        elif ext_lower == ".webp":
            fmt = "WEBP"
        elif ext_lower == ".gif":
            fmt = "GIF"
        else:
            fmt = image.format or "PNG"

        clean_img.save(out, format=fmt)
        return out.getvalue()
    except Exception:
        return contents


# RFC 6238 Standard TOTP Implementation (No external dependency required)

def generate_totp_secret() -> str:
    """Generate a random 32-character Base32 TOTP secret."""
    random_bytes = secrets.token_bytes(20)
    return base64.b32encode(random_bytes).decode("utf-8").replace("=", "")


def get_totp_token(secret: str, interval: int = 30) -> str:
    """Generate current 6-digit TOTP token for secret."""
    secret_bytes = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
    counter = int(time.time()) // interval
    msg = struct.pack(">Q", counter)
    digest = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = ((struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000)
    return f"{code:06d}"


def verify_totp_code(secret: str, code: str, window: int = 1) -> bool:
    """Verify TOTP code with time drift tolerance window."""
    if not secret or not code:
        return False

    clean_code = str(code).strip()
    secret_bytes = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
    current_time = int(time.time()) // 30

    for i in range(-window, window + 1):
        msg = struct.pack(">Q", current_time + i)
        digest = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        computed_code = f"{((struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000):06d}"
        if hmac.compare_digest(computed_code, clean_code):
            return True

    return False


def generate_backup_codes(count: int = 8) -> Tuple[List[str], str]:
    """Generate backup single-use recovery codes."""
    raw_codes = [secrets.token_hex(4).upper() for _ in range(count)]
    formatted_codes = [f"{c[:4]}-{c[4:]}" for c in raw_codes]
    # Store hashed versions in DB for security
    hashed_str = ",".join([hashlib.sha256(c.encode()).hexdigest() for c in formatted_codes])
    return formatted_codes, hashed_str


def verify_and_consume_backup_code(hashed_codes_str: str, code: str) -> Tuple[bool, str]:
    """Verify emergency backup code and return updated hashed codes string if valid."""
    if not hashed_codes_str or not code:
        return False, hashed_codes_str

    clean_code = str(code).strip().upper().replace(" ", "")
    code_hash = hashlib.sha256(clean_code.encode()).hexdigest()

    hashes = [h.strip() for h in hashed_codes_str.split(",") if h.strip()]
    if code_hash in hashes:
        hashes.remove(code_hash)
        return True, ",".join(hashes)

    return False, hashed_codes_str


# CAPTCHA Security System

from PIL import ImageDraw, ImageFont

def generate_captcha_challenge(expires_in: int = 300) -> Tuple[str, str]:
    """Generates an image CAPTCHA challenge and returns (captcha_id_token, base64_image_data)."""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    text = "".join(secrets.choice(chars) for _ in range(5))

    width, height = 240, 70
    image = Image.new('RGB', (width, height), color=(245, 247, 250))
    draw = ImageDraw.Draw(image)

    # Draw subtle random noise lines
    for _ in range(4):
        x1 = secrets.randbelow(width)
        y1 = secrets.randbelow(height)
        x2 = secrets.randbelow(width)
        y2 = secrets.randbelow(height)
        draw.line([(x1, y1), (x2, y2)], fill=(180, 190, 200), width=1)

    # Draw subtle background dots
    for _ in range(80):
        x = secrets.randbelow(width)
        y = secrets.randbelow(height)
        draw.point((x, y), fill=(160, 170, 180))

    # Render characters with improved spacing and scalable font
    font = None
    font_size = 19
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except Exception:
                pass

    if font is None:
        try:
            font = ImageFont.load_default(size=font_size)
        except TypeError:
            font = ImageFont.load_default()

    is_truetype = font is not None and hasattr(font, "getbbox") and font.__class__.__name__ != "ImageFont"

    char_width = width // (len(text) + 1)
    for i, char in enumerate(text):
        x_base = (i + 1) * char_width + secrets.randbelow(6) - 3
        if is_truetype:
            bbox = font.getbbox(char)
            cw = bbox[2] - bbox[0]
            ch = bbox[3] - bbox[1]
            x = x_base - (cw // 2)
            y = (height - ch) // 2 - 4 + secrets.randbelow(6) - 3
        else:
            x = x_base - 6
            y = (height // 2) - 10 + secrets.randbelow(6) - 3

        color = (secrets.randbelow(60), secrets.randbelow(60), secrets.randbelow(60))
        if is_truetype:
            draw.text((x, y), char, fill=color, font=font)
        else:
            for dx in range(3):
                for dy in range(3):
                    draw.text((x + dx, y + dy), char, fill=color, font=font)

    buf = io.BytesIO()
    image.save(buf, format='PNG')
    image_b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    # Sign token
    expires_at = int(time.time()) + expires_in
    secret_key = os.environ.get("SECRET_KEY", "antisocial_super_secret_jwt_and_session_key_2026_red").encode()
    answer_hash = hashlib.sha256(text.lower().encode()).hexdigest()
    token_payload = f"{expires_at}:{answer_hash}"
    sig = hmac.new(secret_key, token_payload.encode(), hashlib.sha256).hexdigest()
    captcha_id = base64.urlsafe_b64encode(f"{token_payload}:{sig}".encode()).decode()

    return captcha_id, image_b64


def verify_captcha_token(captcha_id: str, user_answer: str) -> Tuple[bool, str]:
    """Verify CAPTCHA ID token against user provided answer."""
    if not captcha_id or not user_answer or not user_answer.strip():
        return False, "CAPTCHA code is required"

    try:
        decoded = base64.urlsafe_b64decode(captcha_id.encode()).decode()
        parts = decoded.split(":")
        if len(parts) != 3:
            return False, "Invalid CAPTCHA token format"

        expires_at_str, answer_hash, sig = parts
        expires_at = int(expires_at_str)

        # Check signature
        secret_key = os.environ.get("SECRET_KEY", "antisocial_super_secret_jwt_and_session_key_2026_red").encode()
        token_payload = f"{expires_at_str}:{answer_hash}"
        expected_sig = hmac.new(secret_key, token_payload.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(sig, expected_sig):
            return False, "Invalid CAPTCHA token signature"

        # Check expiration
        if time.time() > expires_at:
            return False, "CAPTCHA has expired, please refresh"

        # Check answer
        given_hash = hashlib.sha256(user_answer.strip().lower().encode()).hexdigest()
        if not hmac.compare_digest(given_hash, answer_hash):
            return False, "Incorrect CAPTCHA solution"

        return True, "OK"
    except Exception:
        return False, "Invalid CAPTCHA token"

