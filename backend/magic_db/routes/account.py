"""Registration, login, passwords, profile and team: /auth/*, /me, /team.

The login lives in an httpOnly cookie (mo_session, path=/). It is never put in a response body.
API clients that are not browsers may send the same value in an X-Session-Token header.
"""
import secrets
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth, config, credits
from ..auth import Current, current
from ..db import get_db
from ..models import Account, AccountMember, LoginSession, User
from ..schemas import (InviteIn, LoginIn, MeIn, OtpSendIn, OtpVerifyIn, PasswordChangeIn, PasswordResetIn,
                       RegisterIn)
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


@router.post("/team/invite")
def invite(body: InviteIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    """Add a designer by mobile number. If no password is given, a temporary one is made and returned
    once, for the owner to share (for example on WhatsApp). The designer can change it after logging in."""
    cur.require_owner()
    plan = credits.plan_of(db, cur.account_id)
    seats = db.scalar(select(func.count()).select_from(AccountMember)
                      .where(AccountMember.account_id == cur.account_id))
    if seats >= plan.seats:
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
    db.commit()
    out = {"ok": True}
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
