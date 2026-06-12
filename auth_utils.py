import base64
import hashlib
import hmac
import json
import time


AUTH_COOKIE_NAME = "k12_helper_auth"
AUTH_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
AUTH_TOKEN_MAX_LENGTH = 512
AUTH_TOKEN_VERSION = 1


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def _sign_payload(payload_b64: str, access_code: str) -> str:
    key = hashlib.sha256(f"k12-helper-auth-v1:{access_code}".encode("utf-8")).digest()
    signature = hmac.new(key, payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64url_encode(signature)


def create_remember_token(access_code: str, now: int | None = None) -> str:
    if not access_code:
        raise ValueError("access_code is required")

    issued_at = int(now or time.time())
    payload = {
        "v": AUTH_TOKEN_VERSION,
        "iat": issued_at,
        "exp": issued_at + AUTH_COOKIE_MAX_AGE_SECONDS,
    }
    payload_b64 = _b64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    return f"{payload_b64}.{_sign_payload(payload_b64, access_code)}"


def validate_remember_token(
    token: str | None,
    access_code: str,
    now: int | None = None,
) -> bool:
    if not token or not access_code or len(token) > AUTH_TOKEN_MAX_LENGTH:
        return False

    parts = token.split(".")
    if len(parts) != 2:
        return False

    payload_b64, signature = parts
    expected_signature = _sign_payload(payload_b64, access_code)
    if not hmac.compare_digest(signature, expected_signature):
        return False

    try:
        payload = json.loads(_b64url_decode(payload_b64))
        version = int(payload.get("v", 0))
        expires_at = int(payload.get("exp", 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        return False

    return version == AUTH_TOKEN_VERSION and expires_at > int(now or time.time())
