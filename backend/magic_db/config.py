"""Settings, read from the environment or from a .env file (backend/.env, then magic_db/.env).

Real environment variables always win over the .env file, the same way perfect.py does it.
"""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_env():
    for env in (HERE.parent / ".env", HERE / ".env"):
        if not env.exists():
            continue
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name, default=False):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------ database
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://magic:magic@127.0.0.1:5432/magic_outline")

# ------------------------------------------------------------------ image storage (MinIO / Contabo / any S3)
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "s3")          # s3 | local
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "http://127.0.0.1:9000")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "magicadmin")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "magicadmin123")
S3_BUCKET = os.environ.get("S3_BUCKET", "magic-outline")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")
LOCAL_STORAGE_DIR = Path(os.environ.get("LOCAL_STORAGE_DIR", str(HERE.parent / "storage_data")))

# Images reach the browser through the backend: /api/files/<key>?e=<expiry>&s=<signature>.
# The Next.js proxy serves the backend's /api/* at /api/backend/*, so that is the default prefix.
FILES_URL_PREFIX = os.environ.get("FILES_URL_PREFIX", "/api/backend/files").rstrip("/")
FILE_LINK_MINUTES = _int("FILE_LINK_MINUTES", 60)
MAX_IMAGE_MB = _int("MAX_IMAGE_MB", 20)

# ------------------------------------------------------------------ security
API_TOKEN = os.environ.get("API_TOKEN", "")                # same shared secret as backend/api.py
SECRET_KEY = os.environ.get("SECRET_KEY", "")              # signs file links and OTP hashes
if not SECRET_KEY:
    SECRET_KEY = "dev-only-secret-change-me"
SESSION_DAYS = _int("SESSION_DAYS", 30)
SESSION_COOKIE = "mo_session"                              # httpOnly, path=/, no Domain
COOKIE_SECURE = _bool("COOKIE_SECURE")                     # set 1 on the live https site
SESSION_HEADER = "x-session-token"
# Local development only: with no login, act as this phone number (created on first use).
DEV_LOGIN_PHONE = os.environ.get("DEV_LOGIN_PHONE", "")

# ------------------------------------------------------------------ password login
PASSWORD_MIN_LENGTH = _int("PASSWORD_MIN_LENGTH", 8)
LOGIN_MAX_FAILS = _int("LOGIN_MAX_FAILS", 5)               # wrong passwords before a short lock
LOGIN_LOCK_MINUTES = _int("LOGIN_LOCK_MINUTES", 15)

# ------------------------------------------------------------------ OTP (login and "forgot password")
SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "console")   # console = OTP printed in the server log
OTP_DEV_ECHO = _bool("OTP_DEV_ECHO")                       # 1 = also return the code in the API reply (dev only)
OTP_MINUTES = _int("OTP_MINUTES", 10)
OTP_MAX_PER_HOUR = _int("OTP_MAX_PER_HOUR", 5)
OTP_MAX_ATTEMPTS = _int("OTP_MAX_ATTEMPTS", 5)

# ------------------------------------------------------------------ credits and payments
# Approved price list (Magic Outline pricing plans, 22 Oct 2026). Chat edits are free.
CREDIT_COST = {
    "single_layer": 1,       # gpt-image-1-mini, 1 or 2 colours
    "multi_colour": 3,       # gpt-image-2.5-sunburst, medium
    "multi_colour_hd": 9,    # gpt-image-2.5-sunburst, high (Pro and Studio only)
    "chat": 0,
}
CREDIT_LABEL = {
    "single_layer": "Single-layer outline",
    "multi_colour": "Multi-colour outline",
    "multi_colour_hd": "Multi-colour HD outline",
    "chat": "Chat edit",
}
TOP_UP_CREDITS = _int("TOP_UP_CREDITS", 50)
TOP_UP_PRICE_INR = _int("TOP_UP_PRICE_INR", 249)
HOLD_MINUTES = _int("HOLD_MINUTES", 15)                    # a reserve not settled by then is given back
PAYMENTS_MODE = os.environ.get("PAYMENTS_MODE", "off")      # off = buttons only | fake = apply at once (dev)

# ------------------------------------------------------------------ AI summaries (text model)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_SUMMARY_MODEL = os.environ.get("OPENAI_SUMMARY_MODEL", os.environ.get("OPENAI_CHAT_MODEL", "gpt-4.1-mini"))  # gpt-4.1-nano is retired
CHAT_LAST_MESSAGES = 6          # sent word for word
CHAT_SUMMARISE_AFTER = 10       # unsummarised messages before the older ones are folded into the summary

HIDDEN_RULES = ("Black outline on a white background. Closed shapes. One line thickness. "
                "Keep every motif in place.")
