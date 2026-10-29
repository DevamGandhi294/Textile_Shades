"""Turn rows into the JSON shapes the frontend expects (frontend/lib/api/types.ts)."""
import uuid
from collections import defaultdict
from typing import Dict, Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import storage
from .models import (Account, Chat, ChatMessage, CreditHold, Design, DesignVersion, Export, Party,
                     PartyReference, Plan, Subscription, User, VersionLayer)


def as_uuid(value, what="item") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        raise HTTPException(404, f"{what.capitalize()} not found.")


def iso(d):
    return d.isoformat() if d else None


def num(v):
    return float(v) if v is not None else None


def user_out(u: User) -> dict:
    return {"id": str(u.id), "phone": u.phone, "email": u.email, "full_name": u.full_name,
            "has_password": bool(u.password_hash), "created_at": iso(u.created_at), "last_login_at": iso(u.last_login_at)}


def account_out(a: Account) -> dict:
    return {"id": str(a.id), "business_name": a.business_name, "gstin": a.gstin, "email": a.email,
            "address": a.address,
            "city": a.city, "state": a.state, "pincode": a.pincode, "created_at": iso(a.created_at)}


def plan_out(p: Plan) -> dict:
    return {"id": p.id, "name": p.name, "tagline": p.tagline, "monthly_credits": p.monthly_credits,
            "one_time_credits": p.one_time_credits, "seats": p.seats, "max_parties": p.max_parties,
            "price_month_inr": num(p.price_month_inr), "price_year_inr": num(p.price_year_inr),
            "storage_mb": p.storage_mb, "retention_days": p.retention_days,
            "carry_over_months": p.carry_over_months, "hd_allowed": p.hd_allowed, "watermark": p.watermark,
            "commercial_use": p.commercial_use, "top_up_allowed": p.top_up_allowed,
            "chat_edits_per_photo": p.chat_edits_per_photo, "redraws_per_photo": p.redraws_per_photo,
            "is_trial": p.is_trial, "features": list(p.features or [])}


def subscription_out(s: Subscription) -> dict:
    return {"id": str(s.id), "plan_id": s.plan_id, "period": s.period, "status": s.status,
            "current_start": iso(s.current_start), "current_end": iso(s.current_end),
            "next_credits_at": iso(s.next_grant_at)}


# ------------------------------------------------------------------ designs

def version_out(v: DesignVersion, layer_count: int = 0) -> dict:
    return {"id": str(v.id), "design_id": str(v.design_id), "parent_id": str(v.parent_id) if v.parent_id else None,
            "kind": v.kind, "label": v.label, "note": v.note,
            "image_url": storage.url_for(v.storage_key), "thumb_url": storage.url_for(v.thumb_key or v.storage_key),
            "width_px": v.width_px, "height_px": v.height_px, "dpi": v.dpi,
            "width_mm": num(v.width_mm), "height_mm": num(v.height_mm), "settings": v.settings,
            "closed_boxes": v.closed_boxes, "gaps_joined": v.gaps_joined, "credits": v.credits,
            "size_bytes": v.size_bytes, "layer_count": layer_count,     # saved layers (PSD can be made again)
            "chat_message_id": str(v.chat_message_id) if v.chat_message_id else None,
            "created_at": iso(v.created_at)}


def designs_out(db: Session, designs: List[Design]) -> List[dict]:
    """Many designs at once, with versions, chat counts, credits and last exports (no N+1 queries)."""
    if not designs:
        return []
    ids = [d.id for d in designs]
    versions = defaultdict(list)
    for v in db.scalars(select(DesignVersion).where(DesignVersion.design_id.in_(ids))
                        .order_by(DesignVersion.created_at, DesignVersion.id)):
        versions[v.design_id].append(v)
    layer_count = dict(db.execute(select(VersionLayer.version_id, func.count())
                                  .where(VersionLayer.version_id.in_([v.id for vs in versions.values() for v in vs]),
                                         VersionLayer.mask_key.is_not(None))
                                  .group_by(VersionLayer.version_id)).all())
    chat_count = dict(db.execute(select(Chat.design_id, func.count()).where(Chat.design_id.in_(ids))
                                 .group_by(Chat.design_id)).all())
    charged = dict(db.execute(select(CreditHold.design_id, func.sum(CreditHold.credits))
                              .where(CreditHold.design_id.in_(ids), CreditHold.status == "charged")
                              .group_by(CreditHold.design_id)).all())
    exports = defaultdict(list)
    for design_id, fmt in db.execute(
            select(DesignVersion.design_id, Export.format).join(Export, Export.version_id == DesignVersion.id)
            .where(DesignVersion.design_id.in_(ids)).order_by(Export.created_at.desc())):
        if fmt not in exports[design_id]:
            exports[design_id].append(fmt)
    out = []
    for d in designs:
        vs = versions[d.id]
        out.append({
            "id": str(d.id), "party_id": str(d.party_id) if d.party_id else None, "name": d.name,
            "current_version_id": str(d.current_version_id) if d.current_version_id else None,
            "created_at": iso(d.created_at), "updated_at": iso(d.updated_at),
            "versions": [version_out(v, layer_count.get(v.id, 0)) for v in vs],
            "chat_count": chat_count.get(d.id, 0),
            "credits_used": int(charged.get(d.id) or sum(v.credits for v in vs)),
            "last_exports": exports[d.id][:3],
        })
    return out


# ------------------------------------------------------------------ parties

def parties_out(db: Session, parties: List[Party]) -> List[dict]:
    if not parties:
        return []
    ids = [p.id for p in parties]
    design_count = dict(db.execute(select(Design.party_id, func.count()).where(Design.party_id.in_(ids))
                                   .group_by(Design.party_id)).all())
    last_design = dict(db.execute(select(Design.party_id, func.max(Design.updated_at))
                                  .where(Design.party_id.in_(ids)).group_by(Design.party_id)).all())
    chat_count = dict(db.execute(select(Chat.party_id, func.count()).where(Chat.party_id.in_(ids))
                                 .group_by(Chat.party_id)).all())
    last_chat = dict(db.execute(select(Chat.party_id, func.max(Chat.last_message_at))
                                .where(Chat.party_id.in_(ids)).group_by(Chat.party_id)).all())
    raw_count = dict(db.execute(select(Design.party_id, func.count())
                                .join(DesignVersion, DesignVersion.design_id == Design.id)
                                .where(Design.party_id.in_(ids), DesignVersion.kind == "raw")
                                .group_by(Design.party_id)).all())
    refs: Dict[uuid.UUID, List[str]] = defaultdict(list)
    for r in db.scalars(select(PartyReference).where(PartyReference.party_id.in_(ids))
                        .order_by(PartyReference.position)):
        refs[r.party_id].append(str(r.version_id))
    out = []
    for p in parties:
        times = [t for t in (p.created_at, last_design.get(p.id), last_chat.get(p.id)) if t]
        out.append({
            "id": str(p.id), "name": p.name, "contact_person": p.contact_person, "phone": p.phone,
            "area": p.area, "gstin": p.gstin, "usual_motifs": p.usual_motifs, "border_width": p.border_width,
            "line_thickness": p.line_thickness, "software": p.software,
            "default_formats": list(p.default_formats or []),
            "ai_summary": p.ai_summary, "ai_summary_auto": p.ai_summary_auto,
            "ai_summary_updated": iso(p.ai_summary_updated), "archived": p.archived,
            "created_at": iso(p.created_at),
            "design_count": design_count.get(p.id, 0), "chat_count": chat_count.get(p.id, 0),
            "raw_count": raw_count.get(p.id, 0), "last_activity_at": iso(max(times)),
            "reference_version_ids": refs[p.id],
        })
    return out


# ------------------------------------------------------------------ chats

def message_out(m: ChatMessage) -> dict:
    return {"id": str(m.id), "chat_id": str(m.chat_id), "role": m.role, "content": m.content,
            "attachment_version_id": str(m.attachment_version_id) if m.attachment_version_id else None,
            "final_prompt": m.final_prompt, "model_label": m.model_label, "credits_used": m.credits_used,
            "created_at": iso(m.created_at)}


def chats_out(db: Session, chats: Iterable[Chat]) -> List[dict]:
    chats = list(chats)
    if not chats:
        return []
    ids = [c.id for c in chats]
    msgs = defaultdict(list)
    for m in db.scalars(select(ChatMessage).where(ChatMessage.chat_id.in_(ids))
                        .order_by(ChatMessage.created_at, ChatMessage.id)):
        msgs[m.chat_id].append(m)
    attached = {m.attachment_version_id for ms in msgs.values() for m in ms if m.attachment_version_id}
    labels = dict(db.execute(select(DesignVersion.id, DesignVersion.label)
                             .where(DesignVersion.id.in_(attached))).all()) if attached else {}
    out = []
    for c in chats:
        ms = msgs[c.id]
        made = [labels[m.attachment_version_id] for m in ms
                if m.attachment_version_id in labels and m.role == "assistant"]
        credits = sum(m.credits_used for m in ms)
        result = f"Made {', '.join(made)}" if made else "Made nothing yet"
        out.append({
            "id": str(c.id), "party_id": str(c.party_id) if c.party_id else None,
            "design_id": str(c.design_id) if c.design_id else None, "title": c.title, "summary": c.summary,
            "last_message_at": iso(c.last_message_at), "created_at": iso(c.created_at),
            "messages": [message_out(m) for m in ms],
            "result_label": f"{result} · {credits} credit{'' if credits == 1 else 's'}",
        })
    return out


def get_owned(db: Session, model, id_value, account_id, what: Optional[str] = None):
    """Load a row by id that belongs to this shop, or 404. Never leaks another shop's rows."""
    row = db.get(model, as_uuid(id_value, what or model.__tablename__.rstrip("s")))
    if row is None or row.account_id != account_id:
        raise HTTPException(404, f"{(what or model.__tablename__.rstrip('s')).capitalize()} not found.")
    return row
