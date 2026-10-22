"""Plans, credits and billing: /plans, /billing, /credits, /payments.

Payments are buttons only for now (PAYMENTS_MODE=off): plan change and top-up answer 501 with a
friendly message. PAYMENTS_MODE=fake applies them at once, for local testing. Sell by hand with:
    python -m magic_db set-plan +919825012345 pro
    python -m magic_db grant +919825012345 50
"""
import hashlib
import hmac
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, credits, storage
from ..auth import Current, current
from ..db import get_db
from ..models import CreditHold, CreditLedger, Design, Invoice, Party, Plan
from ..schemas import BillingPatch, PlanChangeIn, ReserveIn, SettleIn, TopUpIn
from ..serialize import get_owned, iso, num, plan_out, subscription_out

router = APIRouter()

SHOWN_REASON = {"reserve": "ai_call", "release": "refund", "trial_grant": "plan_grant"}


@router.get("/plans")
def plans(db: Session = Depends(get_db)):
    rows = db.scalars(select(Plan).where(Plan.active.is_(True)).order_by(Plan.sort_order))
    return [plan_out(p) for p in rows]


@router.get("/billing")
def billing(cur: Current = Depends(current), db: Session = Depends(get_db)):
    sub = credits.subscription(db, cur.account_id)
    plan = sub.plan if sub else db.get(Plan, "free")
    used_bytes = credits.storage_used_bytes(db, cur.account_id)
    return {
        "subscription": subscription_out(sub) if sub else None,
        "plan": plan_out(plan),
        "credits": {"balance": credits.balance(db, cur.account_id),
                    "used_this_period": credits.used_this_period(db, cur.account_id),
                    "plan_credits": plan.monthly_credits or plan.one_time_credits,
                    "warn_at": cur.account.credit_warn_at},
        "storage": {"used_mb": round(used_bytes / 1024 / 1024, 1), "limit_mb": plan.storage_mb},
        "credit_cost": config.CREDIT_COST,
        "payments_enabled": config.PAYMENTS_MODE != "off",
    }


@router.patch("/billing")
def patch_billing(body: BillingPatch, cur: Current = Depends(current), db: Session = Depends(get_db)):
    cur.account.credit_warn_at = body.warn_at
    db.commit()
    return {"ok": True}


@router.get("/billing/usage")
def usage(cur: Current = Depends(current), db: Session = Depends(get_db)):
    """Recent credit changes, newest first. A reserve that was given back is hidden with its give-back."""
    rows = db.execute(
        select(CreditLedger, CreditHold.status, Design.name, Party.name)
        .outerjoin(CreditHold, CreditHold.id == CreditLedger.hold_id)
        .outerjoin(Design, Design.id == CreditLedger.design_id)
        .outerjoin(Party, Party.id == Design.party_id)
        .where(CreditLedger.account_id == cur.account_id)
        .order_by(CreditLedger.created_at.desc(), CreditLedger.id.desc()).limit(200)).all()
    out = []
    for row, hold_status, design_name, party_name in rows:
        if row.hold_id and hold_status == "released":
            continue
        out.append({"id": row.id, "change": row.change, "reason": SHOWN_REASON.get(row.reason, row.reason),
                    "label": row.label, "party_name": party_name, "design_name": design_name,
                    "created_at": iso(row.created_at)})
    return out


@router.get("/billing/invoices")
def invoices(cur: Current = Depends(current), db: Session = Depends(get_db)):
    rows = db.scalars(select(Invoice).where(Invoice.account_id == cur.account_id).order_by(Invoice.issued_at.desc()))
    return [{"id": str(i.id), "invoice_no": i.invoice_no, "label": i.label,
             "amount_inr": num(i.payment.amount_inr), "gst_inr": num(i.payment.gst_inr),
             "pdf_url": storage.url_for(i.pdf_key), "issued_at": iso(i.issued_at)} for i in rows]


def _payments_off():
    raise HTTPException(501, "Online payment is coming soon. Please contact us on WhatsApp to change your plan "
                             "or buy credits.")


@router.post("/billing/plan")
def change_plan(body: PlanChangeIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    cur.require_owner()
    if config.PAYMENTS_MODE != "fake":
        _payments_off()
    credits.set_plan(db, cur.account_id, body.plan_id, body.period, user_id=cur.user_id)
    db.commit()
    return {"ok": True}


@router.post("/billing/top-up")
def top_up(body: TopUpIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    cur.require_owner()
    if not credits.plan_of(db, cur.account_id).top_up_allowed:
        raise HTTPException(402, "Extra credits need a paid plan. Upgrade to Starter or above.")
    if config.PAYMENTS_MODE != "fake":
        _payments_off()
    packs = max(1, round(body.credits / config.TOP_UP_CREDITS))
    credits.add(db, cur.account_id, packs * config.TOP_UP_CREDITS, "top_up",
                f"{packs * config.TOP_UP_CREDITS} extra credits", user_id=cur.user_id)
    db.commit()
    return {"balance": credits.balance(db, cur.account_id)}


@router.post("/payments/razorpay/webhook")
async def razorpay_webhook(request: Request):
    """Stub for later. Checks Razorpay's signature; applying the payment is still to be written."""
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(501, "Razorpay is not connected yet.")
    raw = await request.body()
    sig = request.headers.get("x-razorpay-signature", "")
    if not hmac.compare_digest(hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(), sig):
        raise HTTPException(400, "Bad signature.")
    event = json.loads(raw or b"{}").get("event")
    # TODO when Razorpay is connected: on "payment.captured" / "subscription.charged", find the payments
    # row by razorpay_order_id, mark it paid, then credits.set_plan(...) or credits.add(..., "top_up").
    return {"ok": True, "event": event, "applied": False}


# ------------------------------------------------------------------ credits for paid AI calls

@router.post("/credits/reserve")
def reserve(body: ReserveIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    """Take the credits before an AI call (402 when not enough). Settle with /credits/{hold_id}/settle.
    Inside backend/api.py, call magic_db.credits.reserve() / settle() directly instead."""
    design_id = get_owned(db, Design, body.design_id, cur.account_id, "design").id if body.design_id else None
    hold = credits.reserve(db, cur.account_id, body.action, user_id=cur.user_id, design_id=design_id,
                           label=body.label, count=body.count)
    db.commit()
    return {"hold_id": str(hold.id), "cost": hold.credits, "balance": credits.balance(db, cur.account_id)}


@router.post("/credits/{hold_id}/settle")
def settle(hold_id: str, body: SettleIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    """ok=true keeps the credits, ok=false gives them back."""
    hold = get_owned(db, CreditHold, hold_id, cur.account_id, "credit hold")
    credits.settle(db, hold.id, body.ok)
    db.commit()
    return {"status": hold.status, "balance": credits.balance(db, cur.account_id)}
