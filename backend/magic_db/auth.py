"""Login (mobile number + password, or phone OTP), registration helpers, login sessions,
and the `current` dependency every route uses."""
import hashlib
import hmac
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config, credits
from .db import get_db
from .models import Account, AccountMember, LoginSession, OtpCode, User

log = logging.getLogger("magic_db")


def now():
    return datetime.now(timezone.utc)


def normalise_phone(raw: str) -> str:
    """'98250 12345' -> '+919825012345'. Indian numbers by default; other countries need '+'."""
    s = (raw or "").strip()
    digits = re.sub(r"\D", "", s)
    if s.startswith("+"):
        phone = "+" + digits
    elif len(digits) == 10:
        phone = "+91" + digits
    elif len(digits) == 12 and digits.startswith("91"):
        phone = "+" + digits
    else:
        phone = ""
    if not re.fullmatch(r"\+\d{10,15}", phone):
        raise HTTPException(422, "Please enter a valid mobile number.")
    return phone


def _hash(*parts: str) -> str:
    return hmac.new(config.SECRET_KEY.encode(), "\n".join(parts).encode(), hashlib.sha256).hexdigest()


# ------------------------------------------------------------------ passwords and business details

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def clean_gstin(raw: Optional[str]) -> Optional[str]:
    """'24abcde1234f1z5' -> '24ABCDE1234F1Z5'. Empty -> None. Wrong format -> 422."""
    g = re.sub(r"\s", "", raw or "").upper()
    if not g:
        return None
    if not GSTIN_RE.match(g):
        raise HTTPException(422, "GST number looks wrong. It has 15 characters, like 24ABCDE1234F1Z5.")
    return g


def clean_pincode(raw: Optional[str]) -> Optional[str]:
    p = re.sub(r"\s", "", raw or "")
    if not p:
        return None
    if not re.fullmatch(r"[1-9][0-9]{5}", p):
        raise HTTPException(422, "Pincode must be 6 digits.")
    return p


def clean_email(raw: Optional[str]) -> Optional[str]:
    e = (raw or "").strip().lower()
    if not e:
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
        raise HTTPException(422, "Email looks wrong.")
    return e


def hash_password(password: str) -> str:
    if len(password or "") < config.PASSWORD_MIN_LENGTH:
        raise HTTPException(422, f"Password must be at least {config.PASSWORD_MIN_LENGTH} characters.")
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${h.hex()}"


def password_ok(password: str, stored: Optional[str]) -> bool:
    try:
        _, n, r, p, salt, h = (stored or "").split("$")
        got = hashlib.scrypt((password or "").encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(h) // 2)
        return hmac.compare_digest(got.hex(), h)
    except ValueError:
        return False


def check_password_login(db: Session, phone: str, password: str) -> AccountMember:
    """Mobile number + password. Locks the login for a while after too many wrong tries."""
    user = db.scalar(select(User).where(User.phone == phone).with_for_update())
    wrong = HTTPException(401, "Wrong mobile number or password.")
    if user is None:
        raise wrong
    if user.locked_until and user.locked_until > now():
        raise HTTPException(429, "Too many wrong tries. Please wait 15 minutes or use 'Forgot password'.")
    if not user.password_hash:
        raise HTTPException(401, "No password is set for this number yet. Use 'Forgot password' to set one.")
    if not password_ok(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= config.LOGIN_MAX_FAILS:
            user.failed_logins = 0
            user.locked_until = now() + timedelta(minutes=config.LOGIN_LOCK_MINUTES)
        db.commit()
        raise wrong
    user.failed_logins = 0
    user.locked_until = None
    member = membership(db, user)
    if member is None:
        raise HTTPException(401, "This login is not part of any shop now.")
    return member


# ------------------------------------------------------------------ API token (same as backend/api.py)

def check_api_token(authorization: Optional[str] = Header(None)):
    token = config.API_TOKEN
    if token and not hmac.compare_digest((authorization or "").encode(), f"Bearer {token}".encode()):
        raise HTTPException(401, "Not allowed: missing or wrong API token.")


# ------------------------------------------------------------------ OTP

def send_sms(phone: str, code: str):
    if config.SMS_PROVIDER == "console":
        log.warning("OTP for %s is %s (SMS_PROVIDER=console: no SMS was sent)", phone, code)
        return
    # Add MSG91 / Twilio here later; keep the same function name.
    raise HTTPException(503, f"SMS provider '{config.SMS_PROVIDER}' is not set up yet.")


def create_otp(db: Session, phone: str) -> str:
    hour_ago = now() - timedelta(hours=1)
    sent = db.scalar(select(func.count()).select_from(OtpCode)
                     .where(OtpCode.phone == phone, OtpCode.created_at > hour_ago))
    if sent >= config.OTP_MAX_PER_HOUR:
        raise HTTPException(429, "Too many codes asked for this number. Please wait an hour.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(OtpCode(phone=phone, code_hash=_hash(phone, code),
                   expires_at=now() + timedelta(minutes=config.OTP_MINUTES)))
    db.commit()
    send_sms(phone, code)
    return code


def check_otp(db: Session, phone: str, code: str):
    otp = db.scalars(select(OtpCode).where(OtpCode.phone == phone, OtpCode.used_at.is_(None),
                                           OtpCode.expires_at > now())
                     .order_by(OtpCode.created_at.desc()).limit(1).with_for_update()).first()
    if otp is None:
        raise HTTPException(401, "The code has expired. Please ask for a new one.")
    if otp.attempts >= config.OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many wrong tries. Please ask for a new code.")
    otp.attempts += 1
    if not hmac.compare_digest(otp.code_hash, _hash(phone, (code or "").strip())):
        db.commit()
        raise HTTPException(401, "Wrong code. Please check the SMS and try again.")
    otp.used_at = now()


# ------------------------------------------------------------------ users and accounts

def membership(db: Session, user: User) -> Optional[AccountMember]:
    """A user belongs to one shop (the first one they joined)."""
    return db.scalars(select(AccountMember).where(AccountMember.user_id == user.id)
                      .order_by(AccountMember.joined_at).limit(1)).first()


def get_or_create_user(db: Session, phone: str, full_name: Optional[str] = None,
                       business_name: Optional[str] = None) -> AccountMember:
    """Find the user by phone, or sign them up: new user + new shop on the free trial."""
    user = db.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = User(phone=phone, full_name=(full_name or "").strip() or None)
        db.add(user)
        db.flush()
    elif full_name and not user.full_name:
        user.full_name = full_name.strip()
    member = membership(db, user)
    if member is None:
        account = Account(business_name=(business_name or "").strip() or "My shop")
        db.add(account)
        db.flush()
        member = AccountMember(account_id=account.id, user_id=user.id, role="owner")
        db.add(member)
        db.flush()
        credits.start_trial(db, account.id, user.id)
    return member


def start_session(db: Session, member: AccountMember) -> tuple:
    token = secrets.token_urlsafe(32)
    expires = now() + timedelta(days=config.SESSION_DAYS)
    db.add(LoginSession(user_id=member.user_id, account_id=member.account_id,
                        token_hash=_hash("session", token), expires_at=expires))
    member.user.last_login_at = now()
    return token, expires


def end_session(db: Session, token: str):
    s = db.scalar(select(LoginSession).where(LoginSession.token_hash == _hash("session", token)))
    if s:
        db.delete(s)


# ------------------------------------------------------------------ who is calling

@dataclass
class Current:
    user: User
    account: Account
    role: str

    @property
    def account_id(self):
        return self.account.id

    @property
    def user_id(self):
        return self.user.id

    def require_owner(self):
        if self.role != "owner":
            raise HTTPException(403, "Only the shop owner can do this.")


def current(db: Session = Depends(get_db),
            x_session_token: Optional[str] = Header(None),
            mo_session: Optional[str] = Cookie(None)) -> Current:
    """Every route depends on this. Reads the login token from the X-Session-Token header or the
    mo_session cookie. With DEV_LOGIN_PHONE set and no token, acts as that phone (local dev only)."""
    token = x_session_token or mo_session
    if token:
        s = db.scalar(select(LoginSession).where(LoginSession.token_hash == _hash("session", token),
                                                 LoginSession.expires_at > now()))
        if s is None:
            raise HTTPException(401, "Please log in again.")
        if s.last_seen_at is None or s.last_seen_at < now() - timedelta(minutes=10):
            s.last_seen_at = now()
            db.commit()
        member = db.get(AccountMember, (s.account_id, s.user_id))
        if member is None:                                  # removed from the team
            raise HTTPException(401, "Please log in again.")
    elif config.DEV_LOGIN_PHONE:
        member = get_or_create_user(db, normalise_phone(config.DEV_LOGIN_PHONE), "Dev user", "Dev shop")
        db.commit()
    else:
        raise HTTPException(401, "Please log in again.")
    return Current(user=member.user, account=db.get(Account, member.account_id), role=member.role)
