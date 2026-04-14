"""Security helpers shared across routers.

Provides:
  get_client_ip(request)          — real client IP via X-Forwarded-For (Apache proxy)
  sign_member_session(member_id)  — HMAC-SHA256 signed cookie value
  verify_member_session(value)    — returns member_id (int) or None
  get_member_id(request)          — convenience wrapper
  sign_admin_session(admin_id)    — HMAC-SHA256 signed admin cookie
  verify_admin_session(value)     — returns admin_id (int) or None
  get_admin_id(request)           — convenience wrapper
"""
import hmac
import hashlib
import base64

from fastapi import Request

_KEY_DIR = "/var/www/pyengines/dullknife_rev1"

# Member session key
_MEMBER_SESSION_KEY_PATH = f"{_KEY_DIR}/.member_session_key"
try:
    with open(_MEMBER_SESSION_KEY_PATH, "rb") as _f:
        _MEMBER_SESSION_KEY = _f.read().strip()
except FileNotFoundError:
    _MEMBER_SESSION_KEY = b""

# Admin session key
_ADMIN_SESSION_KEY_PATH = f"{_KEY_DIR}/.admin_session_key"
try:
    with open(_ADMIN_SESSION_KEY_PATH, "rb") as _f:
        _ADMIN_SESSION_KEY = _f.read().strip()
except FileNotFoundError:
    _ADMIN_SESSION_KEY = b""


def get_client_ip(request: Request) -> str:
    """Return the real client IP from X-Forwarded-For or fallback."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


# ── Member sessions ─────────────────────────────────────────────────────────

def sign_member_session(member_id: int) -> str:
    """Return a signed cookie value of the form '{id}.{base64url(hmac)}'."""
    msg = str(member_id).encode()
    sig = hmac.new(_MEMBER_SESSION_KEY, msg, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{member_id}.{sig_b64}"


def verify_member_session(cookie_value: str):
    """Verify a signed member_id cookie. Returns member_id (int) on success, None otherwise."""
    if not cookie_value or "." not in cookie_value:
        return None
    try:
        member_id_str, sig_b64 = cookie_value.split(".", 1)
        member_id = int(member_id_str)
    except (ValueError, TypeError):
        return None
    expected = hmac.new(_MEMBER_SESSION_KEY, member_id_str.encode(), hashlib.sha256).digest()
    expected_b64 = base64.urlsafe_b64encode(expected).rstrip(b"=").decode()
    if not hmac.compare_digest(expected_b64, sig_b64):
        return None
    return member_id


def get_member_id(request: Request):
    """Convenience: read 'member_id' cookie, verify, return int or None."""
    return verify_member_session(request.cookies.get("member_id", ""))


# ── Admin sessions ───────────────────────────────────────────────────────────

def sign_admin_session(admin_id: int) -> str:
    """Return a signed cookie value of the form '{id}.{base64url(hmac)}'."""
    msg = str(admin_id).encode()
    sig = hmac.new(_ADMIN_SESSION_KEY, msg, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{admin_id}.{sig_b64}"


def verify_admin_session(cookie_value: str):
    """Verify a signed admin_session cookie. Returns admin_id (int) on success, None otherwise."""
    if not cookie_value or "." not in cookie_value:
        return None
    try:
        admin_id_str, sig_b64 = cookie_value.split(".", 1)
        admin_id = int(admin_id_str)
    except (ValueError, TypeError):
        return None
    expected = hmac.new(_ADMIN_SESSION_KEY, admin_id_str.encode(), hashlib.sha256).digest()
    expected_b64 = base64.urlsafe_b64encode(expected).rstrip(b"=").decode()
    if not hmac.compare_digest(expected_b64, sig_b64):
        return None
    return admin_id


def get_admin_id(request: Request):
    """Convenience: read 'admin_session' cookie, verify, return int or None."""
    return verify_admin_session(request.cookies.get("admin_session", ""))
