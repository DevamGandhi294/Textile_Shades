"""Credits: balance, reserve before an AI call, charge or give back after it, plan grants and renewals.

The ledger is append-only. Balance = SUM(change). A paid AI call works like this:

    hold = credits.reserve(db, account_id, "multi_colour", user_id=..., design_id=...)   # -3 now
    db.commit()
    ok = run_the_ai_call()
    credits.settle(db, hold.id, ok)    # ok: keep the 3 credits; failed: +3 back
    db.commit()

reserve() locks the shop's row first, so two requests at the same moment cannot both spend the
last credits.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from . import config
from .models import Account, CreditHold, CreditLedger, DesignVersion, Export, Plan, Subscription


def now():
    return datetime.now(timezone.utc)


def add_months(d: datetime, months: int) -> datetime:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    days = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return d.replace(year=y, month=m, day=min(d.day, days[m - 1]))


# ------------------------------------------------------------------ reading

def balance(db: Session, account_id) -> int:
    return db.scalar(select(func.coalesce(func.sum(CreditLedger.change), 0))
                     .where(CreditLedger.account_id == account_id)) or 0


def subscription(db: Session, account_id) -> Optional[Subscription]:
    """The shop's current subscription (the newest active one, else the newest of any status)."""
    rows = db.scalars(select(Subscription).where(Subscription.account_id == account_id)
                      .order_by((Subscription.status == "active").desc(), Subscription.created_at.desc())
                      .limit(1)).first()
    return rows


def plan_of(db: Session, account_id) -> Plan:
    sub = subscription(db, account_id)
    return sub.plan if sub else db.get(Plan, "free")


def used_this_period(db: Session, account_id) -> int:
    """Credits spent since the last monthly (or trial) grant."""
    since = db.scalar(select(func.max(CreditLedger.created_at))
                      .where(CreditLedger.account_id == account_id,
                             CreditLedger.reason.in_(("plan_grant", "trial_grant"))))
    q = select(func.coalesce(func.sum(CreditLedger.change), 0)).where(
        CreditLedger.account_id == account_id, CreditLedger.reason.in_(("reserve", "release")))
    if since is not None:
        q = q.where(CreditLedger.created_at >= since)
    return -(db.scalar(q) or 0)


def storage_used_bytes(db: Session, account_id) -> int:
    v = db.scalar(select(func.coalesce(func.sum(DesignVersion.size_bytes), 0))
                  .where(DesignVersion.account_id == account_id)) or 0
    e = db.scalar(select(func.coalesce(func.sum(Export.size_bytes), 0))
                  .where(Export.account_id == account_id)) or 0
    return int(v) + int(e)


def check_storage(db: Session, account_id, extra_bytes: int):
    if not config.BILLING_CHECKS:
        return
    plan = plan_of(db, account_id)
    limit = plan.storage_mb * 1024 * 1024
    if storage_used_bytes(db, account_id) + extra_bytes > limit:
        raise HTTPException(402, f"Your storage is full ({plan.storage_mb // 1024 or plan.storage_mb} "
                                 f"{'GB' if plan.storage_mb >= 1024 else 'MB'} on {plan.name}). "
                                 "Delete old designs or upgrade your plan.")


# ------------------------------------------------------------------ writing

def _lock(db: Session, account_id):
    db.execute(select(Account.id).where(Account.id == account_id).with_for_update())


def add(db: Session, account_id, change: int, reason: str, label: str = "", **kw) -> CreditLedger:
    row = CreditLedger(account_id=account_id, change=change, reason=reason, label=label, **kw)
    db.add(row)
    return row


def release_stale(db: Session, account_id=None) -> int:
    """Give back holds that were never settled (the server crashed mid-call)."""
    q = select(CreditHold).where(CreditHold.status == "held", CreditHold.expires_at < now())
    if account_id is not None:
        q = q.where(CreditHold.account_id == account_id)
    n = 0
    for hold in db.scalars(q.with_for_update(skip_locked=True)):
        _give_back(db, hold)
        n += 1
    return n


def reserve(db: Session, account_id, action: str, user_id=None, design_id=None, label: Optional[str] = None,
            count: int = 1) -> CreditHold:
    """Take the credits for `action` now (402 if not enough). Settle with settle() after the call."""
    if action not in config.CREDIT_COST:
        raise HTTPException(422, f"Unknown action '{action}'. Known: {', '.join(config.CREDIT_COST)}.")
    _lock(db, account_id)
    release_stale(db, account_id)
    plan = plan_of(db, account_id)
    if config.BILLING_CHECKS and action == "multi_colour_hd" and not plan.hd_allowed:
        raise HTTPException(402, f"Multi-colour HD needs the Pro or Studio plan. You are on {plan.name}.")
    cost = config.CREDIT_COST[action] * max(1, count)
    if config.BILLING_CHECKS and cost > 0 and balance(db, account_id) < cost:
        raise HTTPException(402, "Not enough credits. Buy extra credits or wait for your plan to renew.")
    text = label or config.CREDIT_LABEL.get(action, action)
    hold = CreditHold(id=uuid.uuid4(), account_id=account_id, user_id=user_id, design_id=design_id, action=action,
                      credits=cost, label=text, expires_at=now() + timedelta(minutes=config.HOLD_MINUTES))
    db.add(hold)
    db.flush()
    if cost:
        add(db, account_id, -cost, "reserve", text, hold_id=hold.id, user_id=user_id, design_id=design_id)
    return hold


def _give_back(db: Session, hold: CreditHold):
    hold.status = "released"
    hold.settled_at = now()
    if hold.credits:
        add(db, hold.account_id, hold.credits, "release", f"{hold.label} (given back)", hold_id=hold.id,
            user_id=hold.user_id, design_id=hold.design_id)


def settle(db: Session, hold_id, ok: bool) -> CreditHold:
    """ok=True keeps the credits; ok=False gives them back. Settling twice does nothing."""
    hold = db.scalar(select(CreditHold).where(CreditHold.id == hold_id).with_for_update())
    if hold is None:
        raise HTTPException(404, "Credit hold not found.")
    if hold.status != "held":
        return hold
    if ok:
        hold.status = "charged"
        hold.settled_at = now()
    else:
        _give_back(db, hold)
    return hold


def start_trial(db: Session, account_id, user_id=None):
    plan = db.get(Plan, "free")
    start = now()
    db.add(Subscription(account_id=account_id, plan_id=plan.id, period="trial", status="active",
                        current_start=start, current_end=start + timedelta(days=plan.retention_days)))
    if plan.one_time_credits:
        add(db, account_id, plan.one_time_credits, "trial_grant", "Free trial credits", user_id=user_id)


def set_plan(db: Session, account_id, plan_id: str, period: str = "monthly", payment_id=None, user_id=None):
    """Move the shop to a plan, start a new period and grant that plan's credits."""
    plan = db.get(Plan, plan_id)
    if plan is None or not plan.active or plan.is_trial:
        raise HTTPException(422, "Unknown plan.")
    _lock(db, account_id)
    db.execute(update(Subscription).where(Subscription.account_id == account_id, Subscription.status == "active")
               .values(status="cancelled"))
    start = now()
    end = add_months(start, 12 if period == "yearly" else 1)
    sub = Subscription(account_id=account_id, plan_id=plan.id, period=period, status="active",
                       current_start=start, current_end=end, next_grant_at=add_months(start, 1))
    db.add(sub)
    add(db, account_id, plan.monthly_credits, "plan_grant", f"{plan.name} plan credits",
        payment_id=payment_id, user_id=user_id)
    return sub


def renew_due(db: Session) -> dict:
    """Run once a day (python -m magic_db renew-due).

    - A paid month has passed and the plan is still paid for: unused credits above the carry-over
      (monthly credits x carry_over_months) expire, then the new month's credits are added.
      Yearly plans get their credits month by month this way.
    - The paid period (current_end) is over: the subscription becomes 'past_due' and gets no credits
      until a payment comes in and set_plan() starts a new period.
    """
    granted = lapsed = 0
    subs = db.scalars(select(Subscription).where(Subscription.status == "active",
                                                 Subscription.period != "trial")).all()
    for sub in subs:
        _lock(db, sub.account_id)
        while sub.next_grant_at and sub.next_grant_at <= now() and sub.next_grant_at < sub.current_end:
            plan = sub.plan
            keep = plan.monthly_credits * plan.carry_over_months
            bal = balance(db, sub.account_id)
            if bal > keep:
                add(db, sub.account_id, -(bal - keep), "expiry", "Unused credits expired")
            add(db, sub.account_id, plan.monthly_credits, "plan_grant", f"{plan.name} plan credits")
            db.flush()
            sub.next_grant_at = add_months(sub.next_grant_at, 1)
            granted += 1
        if sub.current_end <= now():
            sub.status = "past_due"
            lapsed += 1
    return {"granted": granted, "past_due": lapsed}
