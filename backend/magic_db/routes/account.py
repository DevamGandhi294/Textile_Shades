"""Registration, login, passwords, profile and team: /auth/*, /me, /team.

The login lives in an httpOnly cookie (mo_session, path=/). It is never put in a response body.
API clients that are not browsers may send the same value in an X-Session-Token header.
"""
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth, config, credits
from ..auth import Current, current
from ..db import get_db
from ..models import Account, AccountMember, LoginSession, TeamInvite, User
from ..schemas import (GoogleCompleteIn, GoogleIn, InviteCodeIn, InviteIn, LoginIn, MeIn, OtpSendIn, OtpVerifyIn,
                       PasswordChangeIn, PasswordResetIn, RegisterIn)
from ..serialize import account_out, as_uuid, iso, user_out

router = APIRouter()


def me_out(cur: Current) -> dict:
    return {"user": user_out(cur.user), "account": account_out(cur.account), "role": cur.role}


def _log_in(db: Session, response: Response, member: AccountMember) -> dict:
    """Start a login session, set the cookie, return the Me object."""
    token, _ = auth.start_session(db, member)
    db.commit()
    response.set_cookie(config.SESSION_COOKIE, token, max_age=config.SESSION_DAYS * 86400, path="/",
                        httponly=True, samesite="lax", secure=config.COOKIE_SECURE)
    return me_out(Current(user=member.user, account=db.get(Account, member.account_id), role=member.role))


def _session_token(x_session_token: Optional[str] = Header(None), mo_session: Optional[str] = Cookie(None)):
    return x_session_token or mo_session


# ------------------------------------------------------------------ registration and password login

@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)):
    """New shop: owner's mobile number + password, company details. Starts the free trial (100 credits)."""
    phone = auth.normalise_phone(body.phone)
    if db.scalar(select(User.id).where(User.phone == phone)):
        raise HTTPException(409, "This mobile number is already registered. Please log in.")
    email = auth.clean_email(body.email)
    if email and db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "This email is already registered.")
    user = User(phone=phone, full_name=body.owner_name.strip(), email=email,
                password_hash=auth.hash_password(body.password))
    account = Account(business_name=body.company_name.strip(), gstin=auth.clean_gstin(body.gstin), email=email,
                      address=(body.address or "").strip() or None, city=(body.city or "").strip() or None,
                      state=(body.state or "").strip() or None, pincode=auth.clean_pincode(body.pincode))
    db.add_all([user, account])
    db.flush()
    member = AccountMember(account_id=account.id, user_id=user.id, role="owner")
    db.add(member)
    db.flush()
    credits.start_trial(db, account.id, user.id)
    return _log_in(db, response, member)


@router.post("/auth/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    member = auth.check_password_login(db, auth.normalise_phone(body.phone), body.password)
    return _log_in(db, response, member)


@router.get("/auth/google/config")
def google_config():
    """Is Google login on, and with which client id (the website shows the Google button only when it is)."""
    return {"enabled": bool(config.GOOGLE_CLIENT_ID), "client_id": config.GOOGLE_CLIENT_ID or None}


@router.post("/auth/google")
def google_login(body: GoogleIn, response: Response, db: Session = Depends(get_db)):
    """Step 1 of Google login. A known person (their Google account, or the same verified email) is logged in
    at once: {"logged_in": true, "me": ...}. A new person gets {"logged_in": false, "signup_token", "email",
    "full_name"}: send it with the shop details to POST /auth/google/complete."""
    g = auth.verify_google(body.credential)
    user = db.scalar(select(User).where(User.google_sub == g["sub"]))
    if user is None:
        user = db.scalar(select(User).where(func.lower(User.email) == g["email"]))
        if user is not None and user.google_sub is None:
            user.google_sub = g["sub"]                          # same verified email: link Google to it
    if user is not None:
        member = auth.membership(db, user)
        if member is None:
            raise HTTPException(403, "This account is not part of any shop any more.")
        return {"logged_in": True, "me": _log_in(db, response, member)}
    return {"logged_in": False, "signup_token": auth.signup_ticket(g), "email": g["email"], "full_name": g["name"]}


@router.post("/auth/google/complete", status_code=201)
def google_complete(body: GoogleCompleteIn, response: Response, db: Session = Depends(get_db)):
    """Step 2 of Google login for a new person: the shop name and mobile number. Starts the free trial and logs
    in. No password is needed (they log in with Google); they can set one later."""
    g = auth.read_signup_ticket(body.signup_token)
    phone = auth.normalise_phone(body.phone)
    if db.scalar(select(User.id).where(User.phone == phone)):
        raise HTTPException(409, "This mobile number is already registered. Log in with your mobile number and password.")
    if db.scalar(select(User.id).where((User.google_sub == g["sub"]) | (func.lower(User.email) == g["email"]))):
        raise HTTPException(409, "This Google account is already registered. Please sign in with Google again.")
    user = User(phone=phone, email=g["email"], google_sub=g["sub"],
                full_name=(body.owner_name or g["name"] or "").strip() or None)
    account = Account(business_name=body.company_name.strip(), email=g["email"], gstin=auth.clean_gstin(body.gstin),
                      city=(body.city or "").strip() or None)
    db.add_all([user, account])
    db.flush()
    member = AccountMember(account_id=account.id, user_id=user.id, role="owner")
    db.add(member)
    db.flush()
    credits.start_trial(db, account.id, user.id)
    return _log_in(db, response, member)


@router.post("/auth/logout")
def logout(response: Response, db: Session = Depends(get_db), token: Optional[str] = Depends(_session_token)):
    if token:
        auth.end_session(db, token)
        db.commit()
    response.delete_cookie(config.SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/auth/password/change")
def change_password(body: PasswordChangeIn, cur: Current = Depends(current), db: Session = Depends(get_db),
                    token: Optional[str] = Depends(_session_token)):
    """Logged in: change the password. Other logged-in devices are logged out."""
    user = cur.user
    if user.password_hash and not auth.password_ok(body.current_password, user.password_hash):
        raise HTTPException(401, "Your current password is wrong.")
    user.password_hash = auth.hash_password(body.new_password)
    keep = auth._hash("session", token) if token else ""
    db.execute(LoginSession.__table__.delete().where(LoginSession.user_id == user.id,
                                                      LoginSession.token_hash != keep))
    db.commit()
    return {"ok": True}


@router.post("/auth/password/reset/request")
def reset_request(body: OtpSendIn, db: Session = Depends(get_db)):
    """Forgot password, step 1: send a 6-digit code to the phone (printed in the log while SMS_PROVIDER=console).
    Answers the same whether or not the number is registered, so nobody can test which numbers exist."""
    phone = auth.normalise_phone(body.phone)
    out = {"sent": True}
    if db.scalar(select(User.id).where(User.phone == phone)):
        code = auth.create_otp(db, phone)
        if config.OTP_DEV_ECHO:
            out["dev_code"] = code
    return out


@router.post("/auth/password/reset")
def reset_password(body: PasswordResetIn, db: Session = Depends(get_db)):
    """Forgot password, step 2: code + new password. Logs out every device; then log in with the new password."""
    phone = auth.normalise_phone(body.phone)
    new_hash = auth.hash_password(body.new_password)
    try:
        auth.check_otp(db, phone, body.code)
    except HTTPException as e:
        if e.status_code == 401:
            raise HTTPException(400, e.detail)
        raise
    user = db.scalar(select(User).where(User.phone == phone))
    if user is None:
        raise HTTPException(400, "The code has expired. Please ask for a new one.")
    user.password_hash, user.failed_logins, user.locked_until = new_hash, 0, None
    db.execute(LoginSession.__table__.delete().where(LoginSession.user_id == user.id))
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ OTP login (optional, for later SMS)

@router.post("/auth/otp/send")
def otp_send(body: OtpSendIn, db: Session = Depends(get_db)):
    phone = auth.normalise_phone(body.phone)
    code = auth.create_otp(db, phone)
    out = {"sent": True, "expires_in_minutes": config.OTP_MINUTES}
    if config.OTP_DEV_ECHO:
        out["dev_code"] = code
    return out


@router.post("/auth/otp/verify")
def otp_verify(body: OtpVerifyIn, response: Response, db: Session = Depends(get_db)):
    """Log in with an SMS code. A new number gets a new shop on the free trial."""
    phone = auth.normalise_phone(body.phone)
    auth.check_otp(db, phone, body.code)
    member = auth.get_or_create_user(db, phone, body.full_name, body.business_name)
    return _log_in(db, response, member)


# ------------------------------------------------------------------ profile

@router.get("/me")
def get_me(cur: Current = Depends(current)):
    return me_out(cur)


@router.patch("/me")
def patch_me(body: MeIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    user, account = cur.user, cur.account
    if data.get("full_name") is not None:
        user.full_name = data["full_name"].strip() or user.full_name
    if "email" in data:
        email = auth.clean_email(data["email"])
        if email and db.scalar(select(User.id).where(User.email == email, User.id != user.id)):
            raise HTTPException(409, "This email is already used by another login.")
        user.email = email
    shop = {k: data[k] for k in ("business_name", "gstin", "address", "city", "state", "pincode") if k in data}
    if shop:
        cur.require_owner()
        if (shop.get("business_name") or "").strip():
            account.business_name = shop["business_name"].strip()
        if "gstin" in shop:
            account.gstin = auth.clean_gstin(shop["gstin"])
        if "pincode" in shop:
            account.pincode = auth.clean_pincode(shop["pincode"])
        for k in ("address", "city", "state"):
            if k in shop:
                setattr(account, k, (shop[k] or "").strip() or None)
        if "email" in data and cur.role == "owner":
            account.email = user.email
    db.commit()
    return me_out(cur)


# ------------------------------------------------------------------ team

@router.get("/team")
def team(cur: Current = Depends(current), db: Session = Depends(get_db)):
    rows = db.scalars(select(AccountMember).where(AccountMember.account_id == cur.account_id)
                      .order_by(AccountMember.joined_at)).all()
    return [{"user": user_out(m.user), "role": m.role, "joined_at": iso(m.joined_at)} for m in rows]


# ------------------------------------------------------------------ one-time login links for designers

CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"          # no 0/O or 1/I: easy to read out and type


def _clean_code(raw: str) -> str:
    return "".join(ch for ch in (raw or "").upper() if ch in CODE_LETTERS)


def _new_invite(db: Session, cur: Current, user_id) -> dict:
    """A new one-time login link for this designer; earlier unused links of the same designer stop working."""
    db.query(TeamInvite).filter(TeamInvite.account_id == cur.account_id, TeamInvite.user_id == user_id,
                                TeamInvite.used_at.is_(None)).delete()
    plain = "".join(secrets.choice(CODE_LETTERS) for _ in range(10))
    expires = auth.now() + timedelta(days=config.INVITE_DAYS)
    db.add(TeamInvite(account_id=cur.account_id, user_id=user_id, code_hash=auth._hash("invite", plain),
                      expires_at=expires, created_by=cur.user_id))
    code = f"{plain[:5]}-{plain[5:]}"
    return {"invite_code": code, "invite_path": f"/join?code={code}", "invite_expires_at": iso(expires)}


def _open_invite(db: Session, code: str) -> TeamInvite:
    inv = db.scalar(select(TeamInvite).where(TeamInvite.code_hash == auth._hash("invite", _clean_code(code))))
    if inv is None or inv.used_at is not None or inv.expires_at <= auth.now():
        raise HTTPException(404, "This login link is used or expired. Ask the shop owner for a new one.")
    if db.get(AccountMember, (inv.account_id, inv.user_id)) is None:
        raise HTTPException(404, "This designer was removed from the shop.")
    return inv


@router.post("/auth/invite/check")
def invite_check(body: InviteCodeIn, db: Session = Depends(get_db)):
    """Who a login link is for (shown before joining). Does not use the link."""
    inv = _open_invite(db, body.code)
    user, account = db.get(User, inv.user_id), db.get(Account, inv.account_id)
    return {"business_name": account.business_name, "full_name": user.full_name,
            "phone": user.phone[:3] + "*" * (len(user.phone) - 7) + user.phone[-4:],     # +91******2345
            "expires_at": iso(inv.expires_at)}


@router.post("/auth/invite/accept")
def invite_accept(body: InviteCodeIn, response: Response, db: Session = Depends(get_db)):
    """Log the designer in with a login link. The link works ONCE: after that it is refused, and the designer
    logs in with their mobile number and the password the owner set."""
    inv = _open_invite(db, body.code)
    inv.used_at = auth.now()
    member = db.get(AccountMember, (inv.account_id, inv.user_id))
    return _log_in(db, response, member)


@router.post("/team/{user_id}/invite-link")
def invite_link(user_id: str, cur: Current = Depends(current), db: Session = Depends(get_db)):
    """A new one-time login link for a designer of this shop (the old one stops working)."""
    cur.require_owner()
    m = db.get(AccountMember, (cur.account_id, as_uuid(user_id, "member")))
    if m is None or m.role != "designer":
        raise HTTPException(404, "Designer not found.")
    out = {"ok": True, **_new_invite(db, cur, m.user_id)}
    db.commit()
    return out


@router.post("/team/invite")
def invite(body: InviteIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    """Add a designer by mobile number, with the password the owner chooses (if none is given, a temporary
    one is made and returned once). Also returns a one-time login link to share, for example on WhatsApp."""
    cur.require_owner()
    plan = credits.plan_of(db, cur.account_id)
    seats = db.scalar(select(func.count()).select_from(AccountMember)
                      .where(AccountMember.account_id == cur.account_id))
    if config.BILLING_CHECKS and seats >= plan.seats:
        raise HTTPException(402, f"All {plan.seats} seat{'s' if plan.seats != 1 else ''} of {plan.name} are used. "
                                 "Upgrade to add more designers.")
    phone = auth.normalise_phone(body.phone)
    user = db.scalar(select(User).where(User.phone == phone))
    temp = None
    if user is None:
        temp = body.password or secrets.token_urlsafe(6)
        user = User(phone=phone, full_name=(body.full_name or "").strip() or None,
                    password_hash=auth.hash_password(temp))
        db.add(user)
        db.flush()
    elif db.scalar(select(AccountMember).where(AccountMember.user_id == user.id)):
        raise HTTPException(409, "This mobile number already belongs to a shop.")
    db.add(AccountMember(account_id=cur.account_id, user_id=user.id, role="designer"))
    db.flush()
    out = {"ok": True, **_new_invite(db, cur, user.id)}
    db.commit()
    if temp and not body.password:
        out["temp_password"] = temp
    return out


@router.delete("/team/{user_id}")
def remove_member(user_id: str, cur: Current = Depends(current), db: Session = Depends(get_db)):
    cur.require_owner()
    uid = as_uuid(user_id, "member")
    if uid == cur.user_id:
        raise HTTPException(422, "You cannot remove yourself.")
    m = db.get(AccountMember, (cur.account_id, uid))
    if m is None:
        raise HTTPException(404, "Member not found.")
    db.delete(m)
    db.execute(LoginSession.__table__.delete().where(LoginSession.user_id == uid,
                                                      LoginSession.account_id == cur.account_id))
    db.commit()
    return {"ok": True}
