"""Chats: /chats. Every message is kept; only a small context is sent to the AI."""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import credits, summaries
from ..auth import Current, current
from ..db import SessionLocal, get_db
from ..models import Chat, ChatMessage, Design, DesignVersion, Party
from ..schemas import ChatIn, MessageIn
from ..serialize import as_uuid, chats_out, get_owned, message_out

router = APIRouter()


@router.get("/chats")
def list_chats(party_id: Optional[str] = None, design_id: Optional[str] = None, q: Optional[str] = None,
               cur: Current = Depends(current), db: Session = Depends(get_db)):
    stmt = select(Chat).where(Chat.account_id == cur.account_id)
    if party_id:
        stmt = stmt.where(Chat.party_id == as_uuid(party_id, "party"))
    if design_id:
        stmt = stmt.where(Chat.design_id == as_uuid(design_id, "design"))
    if q and q.strip():
        words = select(ChatMessage.chat_id).where(
            ChatMessage.account_id == cur.account_id,
            func.to_tsvector("simple", ChatMessage.content).op("@@")(func.plainto_tsquery("simple", q.strip())))
        stmt = stmt.where(or_(Chat.title.ilike(f"%{q.strip()}%"), Chat.id.in_(words)))
    stmt = stmt.order_by(Chat.last_message_at.desc()).limit(200)
    return chats_out(db, db.scalars(stmt))


@router.get("/chats/{chat_id}")
def get_chat(chat_id: str, cur: Current = Depends(current), db: Session = Depends(get_db)):
    return chats_out(db, [get_owned(db, Chat, chat_id, cur.account_id, "chat")])[0]


@router.post("/chats")
def start_chat(body: ChatIn, cur: Current = Depends(current), db: Session = Depends(get_db)):
    d = get_owned(db, Design, body.design_id, cur.account_id, "design")
    c = Chat(account_id=cur.account_id, party_id=d.party_id, design_id=d.id,
             title=(body.title or "New chat").strip()[:120], created_by=cur.user_id)
    db.add(c)
    db.commit()
    return chats_out(db, [c])[0]


def _after_message(chat_id):
    """Background job: keep the chat summary short, and refresh the party's memory when it changes."""
    with SessionLocal() as db:
        chat = db.get(Chat, chat_id)
        if chat is None:
            return
        if summaries.maybe_summarise_chat(db, chat) and chat.party_id:
            party = db.get(Party, chat.party_id)
            if party and party.ai_summary_auto:
                summaries.rebuild_party_summary(db, party)
        db.commit()


@router.post("/chats/{chat_id}/messages")
def add_message(chat_id: str, body: MessageIn, background: BackgroundTasks,
                cur: Current = Depends(current), db: Session = Depends(get_db)):
    chat = get_owned(db, Chat, chat_id, cur.account_id, "chat")
    attachment = None
    if body.attachment_version_id:
        attachment = get_owned(db, DesignVersion, body.attachment_version_id, cur.account_id, "image").id
    m = ChatMessage(chat_id=chat.id, account_id=cur.account_id, role=body.role, content=body.content,
                    attachment_version_id=attachment, final_prompt=body.final_prompt, model_label=body.model_label,
                    credits_used=max(0, body.credits_used), user_id=cur.user_id if body.role == "user" else None)
    db.add(m)
    db.flush()
    if attachment:      # link the image back to the message that produced it
        v = db.get(DesignVersion, attachment)
        if v.chat_message_id is None:
            v.chat_message_id = m.id
    chat.last_message_at = credits.now()
    if chat.design_id:
        d = db.get(Design, chat.design_id)
        if d:
            d.updated_at = credits.now()
    db.commit()
    background.add_task(_after_message, chat.id)
    return message_out(m)


@router.get("/chats/{chat_id}/ai-context")
def ai_context(chat_id: str, cur: Current = Depends(current), db: Session = Depends(get_db)):
    return summaries.ai_context(db, get_owned(db, Chat, chat_id, cur.account_id, "chat"))


@router.get("/chats/{chat_id}/ai-messages")
def ai_messages(chat_id: str, cur: Current = Depends(current), db: Session = Depends(get_db)):
    """The exact messages to send to the text model (rules + summaries + last 6). For the image backend."""
    return summaries.ai_messages(db, get_owned(db, Chat, chat_id, cur.account_id, "chat"))
