"""Demo data for local testing: python -m magic_db seed-demo [--phone 9999999999]"""
import io
import uuid

from sqlalchemy import select

from . import auth, storage, summaries
from .db import session_scope
from .models import Chat, ChatMessage, Design, DesignVersion, Party


def _png(text: str, dark: bool) -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (800, 500), "white")
    d = ImageDraw.Draw(im)
    for i in range(6):
        d.ellipse((60 + i * 115, 160, 150 + i * 115, 340), outline="black", width=6 if dark else 2)
    d.rectangle((20, 20, 780, 480), outline="black", width=4)
    d.text((30, 30), text, fill="black")
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def seed_demo(phone: str):
    storage.ensure_bucket()
    with session_scope() as db:
        member = auth.get_or_create_user(db, auth.normalise_phone(phone), "Demo owner", "Demo Textiles")
        if not member.user.password_hash:
            member.user.password_hash = auth.hash_password("demo1234")
        acc = member.account_id
        if db.scalar(select(Party.id).where(Party.account_id == acc)):
            print(f"Demo data is already there. Log in with mobile {phone} and password demo1234.")
            return
        shree = Party(account_id=acc, name="Shree Textiles", contact_person="Rameshbhai", area="Ring Road, Surat",
                      usual_motifs="Paisley, peacock", border_width="8-12 cm", line_thickness="medium",
                      software="wilcom", default_formats=["eps", "bmp"])
        laxmi = Party(account_id=acc, name="Laxmi Sarees", area="Varachha", usual_motifs="Mango buta",
                      line_thickness="thin", software="coreldraw", default_formats=["svg"])
        db.add_all([shree, laxmi])
        db.flush()
        for p in (shree, laxmi):
            p.ai_summary = summaries.party_card_summary(p)
            p.ai_summary_updated = summaries.now()
        d = Design(account_id=acc, party_id=shree.id, name="Paisley saree border", created_by=member.user_id)
        db.add(d)
        db.flush()
        parent = None
        for kind, label, note in (("raw", "Raw", "Phone photo"), ("outline", "Outline v1", "46 boxes")):
            vid = uuid.uuid4()
            data = _png(f"{label} (demo)", kind == "outline")
            key = f"acc/{acc}/designs/{d.id}/{vid}/{kind}.png"
            storage.put(key, data, "image/png")
            v = DesignVersion(id=vid, design_id=d.id, account_id=acc, parent_id=parent, kind=kind, label=label,
                              note=note, storage_key=key, content_type="image/png", size_bytes=len(data),
                              width_px=800, height_px=500, dpi=300, width_mm=80, height_mm=50)
            db.add(v)
            db.flush()
            parent = v.id
        d.current_version_id = parent
        c = Chat(account_id=acc, party_id=shree.id, design_id=d.id, title="Clean the sketch")
        db.add(c)
        db.flush()
        db.add_all([
            ChatMessage(chat_id=c.id, account_id=acc, role="user", user_id=member.user_id,
                        content="Clean this sketch. Paisley corners, keep my lines close, 8 cm wide."),
            ChatMessage(chat_id=c.id, account_id=acc, role="assistant", attachment_version_id=parent,
                        content="Outline v1 is ready. 46 closed boxes, 3 gaps joined."),
        ])
    print(f"Demo shop ready. Log in with mobile {phone} and password demo1234.")
