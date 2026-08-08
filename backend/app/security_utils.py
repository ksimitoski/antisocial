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
