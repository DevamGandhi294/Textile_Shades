"""Small AI context: chat summaries, party summaries, and what one AI request contains.

The AI never gets a whole chat history. It gets: hidden rules + party summary (~60 words) +
chat summary + the last 6 messages word for word + the current image. When a chat has more than
CHAT_SUMMARISE_AFTER messages not yet in the summary, the older ones are folded into chat.summary.
"""
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import AiCall, Chat, ChatMessage, Design, DesignVersion, Party

log = logging.getLogger("magic_db")


def now():
    return datetime.now(timezone.utc)


def _ask_text_model(db: Session, account_id, system: str, user: str, max_words: int) -> Optional[str]:
    """One cheap text-model call, logged in ai_calls. None when there is no key or the call fails."""
    if not config.OPENAI_API_KEY:
        return None
    t0 = time.time()
    call = AiCall(account_id=account_id, purpose="summary", provider="openai", model=config.OPENAI_SUMMARY_MODEL,
                  status="failed")
    try:
        r = httpx.post("https://api.openai.com/v1/chat/completions", timeout=60,
                       headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                       json={"model": config.OPENAI_SUMMARY_MODEL,
                             "messages": [{"role": "system", "content": f"{system} Use at most {max_words} words."},
                                          {"role": "user", "content": user}]})
        r.raise_for_status()
        data = r.json()
        usage = data.get("usage") or {}
        call.input_tokens, call.output_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
        call.status = "ok"
        return (data["choices"][0]["message"]["content"] or "").strip() or None
    except Exception as e:                                   # summaries are optional: never break the request
        call.error = str(e)[:500]
        log.warning("summary call failed: %s", e)
        return None
    finally:
        call.duration_ms = int((time.time() - t0) * 1000)
        db.add(call)


def ordered_messages(db: Session, chat_id) -> List[ChatMessage]:
    return list(db.scalars(select(ChatMessage).where(ChatMessage.chat_id == chat_id)
                           .order_by(ChatMessage.created_at, ChatMessage.id)))


def maybe_summarise_chat(db: Session, chat: Chat) -> bool:
    """Fold older messages into chat.summary when too many are waiting. Keeps the last 6 out of it."""
    msgs = ordered_messages(db, chat.id)
    waiting = len(msgs) - chat.summarised_count
    if waiting <= config.CHAT_SUMMARISE_AFTER:
        return False
    upto = len(msgs) - config.CHAT_LAST_MESSAGES
    new = msgs[chat.summarised_count:upto]
    lines = "\n".join(f"{m.role}: {m.content}" for m in new)
    text = _ask_text_model(
        db, chat.account_id,
        "You keep a running summary of a chat between a textile designer and an AI that redraws "
        "embroidery and saree border sketches. Keep requests, decisions, sizes and preferences.",
        f"Summary so far:\n{chat.summary or '(none)'}\n\nNew messages:\n{lines}\n\nWrite the updated summary.",
        120)
    if text is None:
        return False
    chat.summary = text
    chat.summarised_count = upto
    return True


def party_card_summary(p: Party) -> str:
    """A plain summary from the party card, used when there is no AI key."""
    bits = []
    if p.usual_motifs:
        bits.append(f"Usual motifs: {p.usual_motifs}.")
    if p.border_width:
        bits.append(f"Border width {p.border_width}.")
    if p.line_thickness:
        bits.append(f"{p.line_thickness.capitalize()} lines.")
    if p.software:
        bits.append(f"Uses {p.software}.")
    if p.default_formats:
        bits.append(f"Wants {', '.join(f.upper() for f in p.default_formats)} files.")
    return " ".join(bits) or f"{p.name}: no preferences saved yet."


def rebuild_party_summary(db: Session, party: Party) -> str:
    chats = db.scalars(select(Chat).where(Chat.party_id == party.id).order_by(Chat.last_message_at.desc())
                       .limit(10)).all()
    notes = []
    for c in chats:
        if c.summary:
            notes.append(c.summary)
        else:
            notes.extend(m.content for m in ordered_messages(db, c.id) if m.role == "user")
    card = party_card_summary(party)
    text = None
    if notes:
        text = _ask_text_model(
            db, party.account_id,
            "Write what an AI designer should remember about this textile customer: motifs, sizes, line "
            "style, software and file formats. Plain sentences.",
            f"Customer: {party.name}\nCard: {card}\nRecent requests:\n" + "\n".join(notes)[:6000], 60)
    party.ai_summary = text or card
    party.ai_summary_updated = now()
    return party.ai_summary


def ai_context(db: Session, chat: Chat) -> dict:
    """What one AI request contains (Chats -> "What AI will see")."""
    party = db.get(Party, chat.party_id) if chat.party_id else None
    msgs = ordered_messages(db, chat.id)
    current = None
    if chat.design_id:
        d = db.get(Design, chat.design_id)
        if d and d.current_version_id:
            v = db.get(DesignVersion, d.current_version_id)
            current = v.label if v else None
    return {
        "hidden_rules": config.HIDDEN_RULES,
        "party_summary": party.ai_summary if party else None,
        "chat_summary": chat.summary,
        "last_messages": min(config.CHAT_LAST_MESSAGES, len(msgs)),
        "current_image": current,
    }


def ai_messages(db: Session, chat: Chat) -> List[dict]:
    """Ready-made input for the text model: use this in the image backend's /chat instead of the full history.

    [{"role": "system", "content": rules + party + summary}, ...last 6 messages...]
    """
    ctx = ai_context(db, chat)
    system = [ctx["hidden_rules"]]
    if ctx["party_summary"]:
        system.append(f"About this customer: {ctx['party_summary']}")
    if ctx["chat_summary"]:
        system.append(f"Earlier in this chat: {ctx['chat_summary']}")
    last = ordered_messages(db, chat.id)[-config.CHAT_LAST_MESSAGES:]
    return [{"role": "system", "content": "\n".join(system)}] + [
        {"role": m.role, "content": m.content} for m in last if m.role in ("user", "assistant")]
