"""Parties (customers): /parties."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import config, credits, summaries
from ..auth import Current, current
from ..db import get_db
from ..models import DesignVersion, Party, PartyReference
from ..schemas import PartyIn, ReferencesIn
from ..serialize import as_uuid, get_owned, parties_out

router = APIRouter()

FIELDS = ("name", "contact_person", "phone", "area", "gstin", "usual_motifs", "border_width", "line_thickness",
          "software", "default_formats", "ai_summary", "ai_summary_auto", "archived")


def _one(db, party):
    return parties_out(db, [party])[0]


def _apply(party: Party, body: PartyIn):
    data = body.model_dump(exclude_unset=True)
    for k in FIELDS:
        if k in data:
            v = data[k]
            if isinstance(v, str):
                v = v.strip() or None
            if k == "name" and not v:
                raise HTTPException(422, "Party name is needed.")
            if k == "default_formats":
                v = [f.strip().lower() for f in (v or []) if f.strip()]
            if k in ("ai_summary_auto", "archived") and v is None:
                continue
            setattr(party, k, v)
    if "ai_summary" in data and "ai_summary_auto" not in data:
        party.ai_summary_auto = False                       # typed by hand: stop auto-updating it


def _save(db: Session, party: Party):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A party with this name already exists.")


@router.get("/parties")
def list_parties(q: Optional[str] = None, archived: Optional[bool] = False,
                 cur: Current = Depends(current), db: Session = Depends(get_db)):
    stmt = select(Party).where(Party.account_id == cur.account_id)
    if archived is not None:
        stmt = stmt.where(Party.archived == archived)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Party.name.ilike(like) | Party.area.ilike(like) | Party.contact_person.ilike(like))
    rows = parties_out(db, list(db.scalars(stmt)))
    rows.sort(key=lambda p: p["last_activity_at"] or "", reverse=True)
    return rows


@router.get("/parties/{party_id}")
def get_party(party_id: str, cur: Current = Depends(current), db: Session = Depends(get_db)):
    return _one(db, get_owned(db, Party, party_id, cur.account_id, "party"))


@router.post("/parties")
def create_party(body: PartyIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    plan = credits.plan_of(db, cur.account_id)
    if config.BILLING_CHECKS and plan.max_parties is not None:
        n = db.scalar(select(func.count()).select_from(Party)
                      .where(Party.account_id == cur.account_id, Party.archived.is_(False)))
        if n >= plan.max_parties:
            raise HTTPException(402, f"{plan.name} allows up to {plan.max_parties} parties. Upgrade for more.")
    party = Party(account_id=cur.account_id, default_formats=[])
    _apply(party, body)
    if not party.name:
        raise HTTPException(422, "Party name is needed.")
    if party.ai_summary is None:
        party.ai_summary = summaries.party_card_summary(party)
        party.ai_summary_updated = summaries.now()
    db.add(party)
    _save(db, party)
    return _one(db, party)


@router.patch("/parties/{party_id}")
def update_party(party_id: str, body: PartyIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    party = get_owned(db, Party, party_id, cur.account_id, "party")
    _apply(party, body)
    if party.ai_summary_auto and not party.ai_summary:
        party.ai_summary = summaries.party_card_summary(party)
        party.ai_summary_updated = summaries.now()
    _save(db, party)
    return _one(db, party)


@router.post("/parties/{party_id}/summary/rebuild")
def rebuild_summary(party_id: str, cur: Current = Depends(current), db: Session = Depends(get_db)):
    """Text model rewrites "What AI remembers" from the card and recent chats (card only without an AI key)."""
    party = get_owned(db, Party, party_id, cur.account_id, "party")
    summaries.rebuild_party_summary(db, party)
    party.ai_summary_auto = True
    db.commit()
    return _one(db, party)


@router.post("/parties/{party_id}/references")
def set_references(party_id: str, body: ReferencesIn, cur: Current = Depends(current),
                   db: Session = Depends(get_db)):
    """Up to 4 favourite images sent to the AI as references, in this order."""
    party = get_owned(db, Party, party_id, cur.account_id, "party")
    ids = list(dict.fromkeys(as_uuid(v, "image") for v in body.version_ids))[:4]
    if ids:
        found = set(db.scalars(select(DesignVersion.id).where(DesignVersion.id.in_(ids),
                                                              DesignVersion.account_id == cur.account_id)))
        if len(found) != len(ids):
            raise HTTPException(404, "Image not found.")
    db.execute(PartyReference.__table__.delete().where(PartyReference.party_id == party.id))
    for pos, vid in enumerate(ids, start=1):
        db.add(PartyReference(party_id=party.id, account_id=cur.account_id, version_id=vid, position=pos))
    db.commit()
    return _one(db, party)
