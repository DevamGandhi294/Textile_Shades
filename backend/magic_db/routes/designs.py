"""Designs and their linked images: /designs."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .. import credits, storage
from ..auth import Current, current
from ..db import get_db
from ..models import (AreaSelection, AreaEditRequest, Chat, ChatMessage, Design, DesignVersion, Export, Party,
                      VersionLayer)
from ..schemas import DesignIn, DesignPatch, ExportIn, LayersIn, SessionIn, VersionIn
from ..serialize import as_uuid, designs_out, get_owned, iso, version_out

router = APIRouter()


def _one(db, d):
    return designs_out(db, [d])[0]


def _owned_party(db, party_id, account_id):
    if not party_id:
        return None
    return get_owned(db, Party, party_id, account_id, "party").id


@router.get("/designs")
def list_designs(party_id: Optional[str] = None, q: Optional[str] = None,
                 cur: Current = Depends(current), db: Session = Depends(get_db)):
    stmt = select(Design).where(Design.account_id == cur.account_id)
    if party_id:
        stmt = stmt.where(Design.party_id == as_uuid(party_id, "party"))
    if q:
        stmt = stmt.where(Design.name.ilike(f"%{q.strip()}%"))
    stmt = stmt.order_by(Design.updated_at.desc()).limit(500)
    return designs_out(db, list(db.scalars(stmt)))


@router.get("/designs/{design_id}")
def get_design(design_id: str, cur: Current = Depends(current), db: Session = Depends(get_db)):
    return _one(db, get_owned(db, Design, design_id, cur.account_id, "design"))


@router.post("/designs")
def create_design(body: DesignIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    d = Design(account_id=cur.account_id, party_id=_owned_party(db, body.party_id, cur.account_id),
               name=body.name.strip(), created_by=cur.user_id)
    db.add(d)
    db.commit()
    return _one(db, d)


@router.patch("/designs/{design_id}")
def update_design(design_id: str, body: DesignPatch, cur: Current = Depends(current), db: Session = Depends(get_db)):
    d = get_owned(db, Design, design_id, cur.account_id, "design")
    data = body.model_dump(exclude_unset=True)
    if data.get("name"):
        d.name = data["name"].strip()
    if "party_id" in data:
        d.party_id = _owned_party(db, data["party_id"], cur.account_id)
        db.execute(Chat.__table__.update().where(Chat.design_id == d.id).values(party_id=d.party_id))
    if data.get("current_version_id"):
        v = get_owned(db, DesignVersion, data["current_version_id"], cur.account_id, "image")
        if v.design_id != d.id:
            raise HTTPException(422, "That image belongs to another design.")
        d.current_version_id = v.id
    d.updated_at = credits.now()
    db.commit()
    return _one(db, d)


@router.delete("/designs/{design_id}")
def delete_design(design_id: str, cur: Current = Depends(current), db: Session = Depends(get_db)):
    """Deletes the design, its images, chats and exports. Files are removed from storage too."""
    d = get_owned(db, Design, design_id, cur.account_id, "design")
    vids = select(DesignVersion.id).where(DesignVersion.design_id == d.id)
    keys = []
    for v in db.scalars(select(DesignVersion).where(DesignVersion.design_id == d.id)):
        keys += [v.storage_key, v.thumb_key]
    keys += db.scalars(select(Export.storage_key).where(Export.version_id.in_(vids))).all()
    keys += db.scalars(select(VersionLayer.mask_key).where(VersionLayer.version_id.in_(vids))).all()
    keys += db.scalars(select(AreaSelection.mask_key).join(AreaEditRequest)
                       .where(AreaEditRequest.version_id.in_(vids))).all()
    d.current_version_id = None
    db.flush()
    db.delete(d)
    db.commit()
    storage.delete(*keys)
    return {"ok": True}


# ------------------------------------------------------------------ images (versions)

def _image_bytes(url: str, account_id) -> tuple:
    """The image sent by the frontend: a data URL, or one of our own links (copied, not shared)."""
    if url.startswith("data:"):
        try:
            return storage.decode_data_url(url) + (None,)
        except storage.BadImage as e:
            raise HTTPException(422, str(e))
    key = storage.key_from_url(url)
    if key is None or not key.startswith(f"acc/{account_id}/"):
        raise HTTPException(422, "The image must be a data URL (data:image/...;base64,...) or a saved image link.")
    data = storage.read(key)
    ext = key.rsplit(".", 1)[-1].lower()
    return data, storage._guess_type(key), ext, key


@router.post("/designs/{design_id}/versions")
def add_version(design_id: str, body: VersionIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    """Save one image of the design (raw, scan, ai or outline). The file goes to storage, the row to Postgres."""
    d = get_owned(db, Design, design_id, cur.account_id, "design")
    parent_id = None
    if body.parent_id:
        parent = get_owned(db, DesignVersion, body.parent_id, cur.account_id, "image")
        if parent.design_id != d.id:
            raise HTTPException(422, "The parent image belongs to another design.")
        parent_id = parent.id
    msg_id = None
    if body.chat_message_id:
        msg_id = get_owned(db, ChatMessage, body.chat_message_id, cur.account_id, "message").id

    data, ctype, ext, _ = _image_bytes(body.image_url, cur.account_id)
    thumb = storage.make_thumb(data) if ctype != "image/svg+xml" else None
    credits.check_storage(db, cur.account_id, len(data) + len(thumb or b""))

    vid = uuid.uuid4()
    base = f"acc/{cur.account_id}/designs/{d.id}/{vid}"
    key, thumb_key = f"{base}/{body.kind}.{ext}", (f"{base}/thumb.jpg" if thumb else None)
    w, h = body.width_px, body.height_px
    if not (w and h):
        w, h = storage.image_size(data)
    storage.put(key, data, ctype)
    if thumb:
        storage.put(thumb_key, thumb, "image/jpeg")
    v = DesignVersion(id=vid, design_id=d.id, account_id=cur.account_id, parent_id=parent_id, kind=body.kind,
                      label=body.label or body.kind.capitalize(), note=body.note, storage_key=key,
                      thumb_key=thumb_key, content_type=ctype, size_bytes=len(data) + len(thumb or b""),
                      width_px=w, height_px=h, dpi=body.dpi, width_mm=body.width_mm, height_mm=body.height_mm,
                      settings=body.settings, closed_boxes=body.closed_boxes, gaps_joined=body.gaps_joined,
                      credits=max(0, body.credits), chat_message_id=msg_id, created_by=cur.user_id)
    db.add(v)
    db.flush()
    if body.make_current or d.current_version_id is None:
        d.current_version_id = v.id
    d.updated_at = credits.now()
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key, thumb_key)
        raise
    return version_out(v)


@router.delete("/designs/{design_id}/versions/{version_id}")
def delete_version(design_id: str, version_id: str, cur: Current = Depends(current), db: Session = Depends(get_db)):
    d = get_owned(db, Design, design_id, cur.account_id, "design")
    v = get_owned(db, DesignVersion, version_id, cur.account_id, "image")
    if v.design_id != d.id:
        raise HTTPException(404, "Image not found.")
    keys = [v.storage_key, v.thumb_key]
    keys += db.scalars(select(Export.storage_key).where(Export.version_id == v.id)).all()
    keys += db.scalars(select(VersionLayer.mask_key).where(VersionLayer.version_id == v.id)).all()  # saved layers
    if d.current_version_id == v.id:
        d.current_version_id = v.parent_id
    db.delete(v)
    db.commit()
    storage.delete(*keys)
    return {"ok": True}


@router.post("/designs/{design_id}/exports")
def record_export(design_id: str, body: ExportIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    """Remember that a file format was downloaded (shown as "Last export: SVG, BMP")."""
    d = get_owned(db, Design, design_id, cur.account_id, "design")
    if not d.current_version_id:
        raise HTTPException(422, "This design has no image yet.")
    fmt = body.format.strip().lower()
    stmt = insert(Export).values(account_id=cur.account_id, version_id=d.current_version_id, format=fmt,
                                 created_by=cur.user_id)
    db.execute(stmt.on_conflict_do_update(constraint="uq_exports_version_format",
                                          set_={"created_at": credits.now(), "created_by": cur.user_id}))
    db.commit()
    return {"ok": True}


@router.get("/designs/{design_id}/session")
def get_image_session(design_id: str, cur: Current = Depends(current), db: Session = Depends(get_db)):
    """Which image backend session (POST /api/sessions) belongs to this design, if any."""
    d = get_owned(db, Design, design_id, cur.account_id, "design")
    return {"sid": d.image_session_id}


@router.post("/designs/{design_id}/session")
def set_image_session(design_id: str, body: SessionIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    d = get_owned(db, Design, design_id, cur.account_id, "design")
    d.image_session_id = body.sid
    db.commit()
    return {"sid": d.image_session_id}


# ------------------------------------------------------------------ colour layers of one image

@router.get("/versions/{version_id}/layers")
def get_layers(version_id: str, cur: Current = Depends(current), db: Session = Depends(get_db)):
    v = get_owned(db, DesignVersion, version_id, cur.account_id, "image")
    rows = db.scalars(select(VersionLayer).where(VersionLayer.version_id == v.id).order_by(VersionLayer.position))
    return [{"id": str(r.id), "position": r.position, "color": r.color, "name": r.name, "visible": r.visible,
             "mask_url": storage.url_for(r.mask_key), "created_at": iso(r.created_at)} for r in rows]


@router.put("/versions/{version_id}/layers")
def put_layers(version_id: str, body: LayersIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    """Save the colour layers' names and visibility (used for layer names in PSD / SVG files)."""
    v = get_owned(db, DesignVersion, version_id, cur.account_id, "image")
    old = {r.position: r for r in db.scalars(select(VersionLayer).where(VersionLayer.version_id == v.id))}
    for pos, layer in enumerate(body.layers, start=1):
        row = old.pop(pos, None) or VersionLayer(account_id=cur.account_id, version_id=v.id, position=pos)
        row.color, row.name, row.visible = layer.color, layer.name.strip() or f"Layer {pos}", layer.visible
        db.add(row)
    for row in old.values():
        db.delete(row)
    db.commit()
    storage.delete(*[r.mask_key for r in old.values()])
    return get_layers(version_id, cur, db)
