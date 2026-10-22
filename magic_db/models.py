"""Magic Outline database tables (SQLAlchemy 2.x ORM).

Images live in object storage (MinIO / Contabo, S3 API). The database stores only keys and details.
Every business table carries account_id so one shop can never see another shop's data.

Change a table here, then make a migration:  python -m magic_db make-migration "what changed"
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (BigInteger, MetaData, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer,
                        Numeric, SmallInteger, Text, UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"),
                         default=uuid.uuid4)


def created_at():
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def account_fk(index=False):
    return mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"),
                         nullable=False, index=index)


# ------------------------------------------------------------------ accounts and users

class Account(Base):                                      # one shop / studio / unit
    __tablename__ = "accounts"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_name: Mapped[str] = mapped_column(Text)
    gstin: Mapped[Optional[str]] = mapped_column(Text)              # checked format, e.g. 24ABCDE1234F1Z5
    email: Mapped[Optional[str]] = mapped_column(Text)              # business email (for invoices)
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(Text)
    state: Mapped[Optional[str]] = mapped_column(Text)
    pincode: Mapped[Optional[str]] = mapped_column(Text)
    credit_warn_at: Mapped[int] = mapped_column(Integer, server_default="20", default=20)
    created_at: Mapped[datetime] = created_at()


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    phone: Mapped[str] = mapped_column(Text, unique=True)  # login by phone OTP, stored as +91XXXXXXXXXX
    email: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    full_name: Mapped[Optional[str]] = mapped_column(Text)
    password_hash: Mapped[Optional[str]] = mapped_column(Text)       # scrypt; NULL = no password set yet
    failed_logins: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AccountMember(Base):                                # team seats
    __tablename__ = "account_members"
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"),
                                                  primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               primary_key=True)
    role: Mapped[str] = mapped_column(Text)
    joined_at: Mapped[datetime] = created_at()
    user: Mapped[User] = relationship(lazy="joined")
    __table_args__ = (CheckConstraint("role IN ('owner','designer')", name="role_ok"),)


class OtpCode(Base):
    __tablename__ = "otp_codes"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(Text)
    code_hash: Mapped[str] = mapped_column(Text)          # never store the plain code
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (Index("ix_otp_codes_phone_created", "phone", "created_at"),)


class LoginSession(Base):                                 # one row per logged-in browser
    __tablename__ = "login_sessions"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[uuid.UUID] = account_fk()
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ------------------------------------------------------------------ plans, credits, billing

class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(Text, primary_key=True)   # 'free' | 'starter' | 'pro' | 'studio'
    name: Mapped[str] = mapped_column(Text)
    tagline: Mapped[str] = mapped_column(Text, server_default="")
    sort_order: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    price_month_inr: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))   # before 18% GST
    price_year_inr: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    monthly_credits: Mapped[int] = mapped_column(Integer)                        # 0 for the free trial
    one_time_credits: Mapped[int] = mapped_column(Integer, server_default="0")   # free trial: 10, once
    seats: Mapped[int] = mapped_column(Integer)
    max_parties: Mapped[Optional[int]] = mapped_column(Integer)                  # NULL = unlimited
    storage_mb: Mapped[int] = mapped_column(Integer)
    retention_days: Mapped[int] = mapped_column(Integer)
    carry_over_months: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    hd_allowed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    watermark: Mapped[bool] = mapped_column(Boolean, server_default="false")     # downloads carry a watermark
    commercial_use: Mapped[bool] = mapped_column(Boolean, server_default="true")
    top_up_allowed: Mapped[bool] = mapped_column(Boolean, server_default="true")
    chat_edits_per_photo: Mapped[int] = mapped_column(Integer, server_default="20")
    redraws_per_photo: Mapped[int] = mapped_column(Integer, server_default="3")
    features: Mapped[List[str]] = mapped_column(ARRAY(Text), server_default="{}")
    is_trial: Mapped[bool] = mapped_column(Boolean, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = account_fk()
    plan_id: Mapped[str] = mapped_column(Text, ForeignKey("plans.id"))
    period: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    current_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))    # paid until ("Renews 1 Nov")
    next_grant_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # next monthly credits
    razorpay_sub_id: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    plan: Mapped[Plan] = relationship(lazy="joined")
    __table_args__ = (
        CheckConstraint("period IN ('trial','monthly','yearly')", name="period_ok"),
        CheckConstraint("status IN ('active','past_due','cancelled')", name="status_ok"),
        Index("ix_subscriptions_account_status", "account_id", "status"),
    )


class CreditHold(Base):
    """Credits set aside while an AI call runs. charged = kept, released = given back."""
    __tablename__ = "credit_holds"
    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = account_fk()
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    design_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("designs.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(Text)
    credits: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="held", default="held")
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('held','charged','released')", name="status_ok"),
        Index("ix_credit_holds_account_status", "account_id", "status"),
    )


class CreditLedger(Base):
    """Append-only: balance = SUM(change). Never update or delete rows."""
    __tablename__ = "credit_ledger"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = account_fk()
    change: Mapped[int] = mapped_column(Integer)           # +470 monthly grant, -3 reserve, +3 release
    reason: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text, server_default="")
    hold_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("credit_holds.id"))
    ai_call_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("ai_calls.id"))
    payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("payments.id"))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    design_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("designs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (
        CheckConstraint("reason IN ('plan_grant','trial_grant','top_up','reserve','release','refund',"
                        "'manual_adjust','expiry')", name="reason_ok"),
        Index("ix_credit_ledger_account_created", "account_id", "created_at"),
    )


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = account_fk(index=True)
    kind: Mapped[str] = mapped_column(Text)
    amount_inr: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    gst_inr: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(Text)
    razorpay_order_id: Mapped[Optional[str]] = mapped_column(Text)
    razorpay_payment_id: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (
        CheckConstraint("kind IN ('subscription','top_up')", name="kind_ok"),
        CheckConstraint("status IN ('created','paid','failed','refunded')", name="status_ok"),
    )


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = account_fk(index=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payments.id"))
    invoice_no: Mapped[str] = mapped_column(Text, unique=True)    # sequential, needed for GST
    label: Mapped[str] = mapped_column(Text, server_default="")
    pdf_key: Mapped[Optional[str]] = mapped_column(Text)          # object storage key
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payment: Mapped[Payment] = relationship(lazy="joined")


# ------------------------------------------------------------------ parties (customers)

class Party(Base):
    __tablename__ = "parties"
    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = account_fk()
    name: Mapped[str] = mapped_column(Text)
    contact_person: Mapped[Optional[str]] = mapped_column(Text)
    phone: Mapped[Optional[str]] = mapped_column(Text)
    area: Mapped[Optional[str]] = mapped_column(Text)
    gstin: Mapped[Optional[str]] = mapped_column(Text)
    # design preferences (party card)
    usual_motifs: Mapped[Optional[str]] = mapped_column(Text)
    border_width: Mapped[Optional[str]] = mapped_column(Text)
    line_thickness: Mapped[Optional[str]] = mapped_column(Text)
    software: Mapped[Optional[str]] = mapped_column(Text)               # 'wilcom' | 'coreldraw' | ...
    default_formats: Mapped[List[str]] = mapped_column(ARRAY(Text), server_default="{}", default=list)
    # "What AI remembers": the ONLY party data sent to the AI
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)              # about 60 words
    ai_summary_auto: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)
    ai_summary_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    archived: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False)
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (
        UniqueConstraint("account_id", "name", name="uq_parties_account_name"),
        CheckConstraint("line_thickness IN ('thin','medium','bold')", name="line_thickness_ok"),
        Index("ix_parties_account_archived", "account_id", "archived"),
    )


class PartyReference(Base):                               # up to 4 favourite designs sent as references
    __tablename__ = "party_references"
    party_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("parties.id", ondelete="CASCADE"),
                                                primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    account_id: Mapped[uuid.UUID] = account_fk(index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                  ForeignKey("design_versions.id", ondelete="CASCADE"))
    __table_args__ = (CheckConstraint("position BETWEEN 1 AND 4", name="position_ok"),)


# ------------------------------------------------------------------ designs and linked images

class Design(Base):
    __tablename__ = "designs"
    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = account_fk()
    party_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("parties.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(Text)                             # "Paisley saree border"
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("design_versions.id", ondelete="SET NULL", use_alter=True,
                                       name="fk_designs_current_version"))
    image_session_id: Mapped[Optional[str]] = mapped_column(Text)       # the image backend's /api/sessions id
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    versions: Mapped[List["DesignVersion"]] = relationship(
        foreign_keys="DesignVersion.design_id", order_by="(DesignVersion.created_at, DesignVersion.id)",
        cascade="all, delete-orphan", passive_deletes=True)
    __table_args__ = (Index("ix_designs_account_party_updated", "account_id", "party_id", "updated_at"),)


class DesignVersion(Base):
    """Every image of a design: raw -> scan -> ai -> outline. parent links them into a chain."""
    __tablename__ = "design_versions"
    id: Mapped[uuid.UUID] = uuid_pk()
    design_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("designs.id", ondelete="CASCADE"))
    account_id: Mapped[uuid.UUID] = account_fk()
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True),
                                                           ForeignKey("design_versions.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text, server_default="")          # "Outline v2"
    note: Mapped[Optional[str]] = mapped_column(Text)                    # "Phone photo", "Mirrored"
    storage_key: Mapped[str] = mapped_column(Text)                       # acc/{account}/designs/{design}/{version}/...
    thumb_key: Mapped[Optional[str]] = mapped_column(Text)               # ~400 px preview
    content_type: Mapped[Optional[str]] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger, server_default="0", default=0)
    width_px: Mapped[Optional[int]] = mapped_column(Integer)
    height_px: Mapped[Optional[int]] = mapped_column(Integer)
    dpi: Mapped[Optional[int]] = mapped_column(Integer)
    width_mm: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    height_mm: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    settings: Mapped[Optional[dict]] = mapped_column(JSONB)              # thickness, gap fill, mirror...
    closed_boxes: Mapped[Optional[int]] = mapped_column(Integer)
    gaps_joined: Mapped[Optional[int]] = mapped_column(Integer)
    credits: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    ai_call_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("ai_calls.id", ondelete="SET NULL", use_alter=True, name="fk_design_versions_ai_call"))
    chat_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="SET NULL", use_alter=True,
                                       name="fk_design_versions_chat_message"))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (
        CheckConstraint("kind IN ('raw','scan','ai','outline')", name="kind_ok"),
        CheckConstraint("dpi IS NULL OR dpi BETWEEN 72 AND 1200", name="dpi_ok"),
        Index("ix_design_versions_design_created", "design_id", "created_at"),
        Index("ix_design_versions_account_kind", "account_id", "kind"),
    )


class VersionLayer(Base):
    """Colour layers found in one outline: their colour, the name used in PSD/SVG files, shown or hidden."""
    __tablename__ = "version_layers"
    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = account_fk(index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("design_versions.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    color: Mapped[str] = mapped_column(Text)                             # '#B91C1C'
    name: Mapped[str] = mapped_column(Text)                              # "Red border"
    visible: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)
    mask_key: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (UniqueConstraint("version_id", "position", name="uq_version_layers_position"),)


class AreaEditRequest(Base):
    """One "Regenerate selected areas" click. Its colours are the area_selections rows."""
    __tablename__ = "area_edit_requests"
    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = account_fk(index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("design_versions.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text, server_default="pending", default="pending")
    credits: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    hold_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("credit_holds.id"))
    result_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True),
                                                                   ForeignKey("design_versions.id", ondelete="SET NULL"))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (CheckConstraint("status IN ('pending','done','failed')", name="status_ok"),)


class AreaSelection(Base):                                # areas painted in the selector, one row per colour
    __tablename__ = "area_selections"
    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = account_fk(index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("area_edit_requests.id", ondelete="CASCADE"))
    color: Mapped[str] = mapped_column(Text)                             # '#2563EB'
    mask_key: Mapped[str] = mapped_column(Text)                          # mask PNG in object storage
    prompt: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class Export(Base):
    __tablename__ = "exports"
    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = account_fk(index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("design_versions.id", ondelete="CASCADE"))
    format: Mapped[str] = mapped_column(Text)                            # svg, eps, pdf, layers-psd ...
    storage_key: Mapped[Optional[str]] = mapped_column(Text)             # NULL = made on the fly, only recorded
    size_bytes: Mapped[int] = mapped_column(BigInteger, server_default="0", default=0)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (UniqueConstraint("version_id", "format", name="uq_exports_version_format"),)


# ------------------------------------------------------------------ chats

class Chat(Base):
    __tablename__ = "chats"
    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = account_fk()
    party_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("parties.id", ondelete="SET NULL"))
    design_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("designs.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text, server_default="")
    summary: Mapped[Optional[str]] = mapped_column(Text)                 # older messages, summarised (sent to AI)
    summarised_count: Mapped[int] = mapped_column(Integer, server_default="0", default=0)  # first N messages are in summary
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at()
    messages: Mapped[List["ChatMessage"]] = relationship(
        order_by="(ChatMessage.created_at, ChatMessage.id)", cascade="all, delete-orphan", passive_deletes=True)
    __table_args__ = (Index("ix_chats_account_party_last", "account_id", "party_id", "last_message_at"),)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[uuid.UUID] = uuid_pk()
    chat_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"))
    account_id: Mapped[uuid.UUID] = account_fk()
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    attachment_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("design_versions.id", ondelete="SET NULL"))   # image shown in chat
    final_prompt: Mapped[Optional[str]] = mapped_column(Text)            # prompt the text model wrote for the image model
    model_label: Mapped[Optional[str]] = mapped_column(Text)             # "gpt-image-2 · medium · 3 credits"
    credits_used: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','system')", name="role_ok"),
        Index("ix_chat_messages_chat_created", "chat_id", "created_at"),
        Index("ix_chat_messages_account_created", "account_id", "created_at"),
        Index("ix_chat_messages_search", text("to_tsvector('simple', content)"), postgresql_using="gin"),
    )


# ------------------------------------------------------------------ AI usage (cost tracking)

class AiCall(Base):
    __tablename__ = "ai_calls"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = account_fk()
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    chat_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True),
                                                                 ForeignKey("chat_messages.id", ondelete="SET NULL"))
    hold_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("credit_holds.id"))
    purpose: Mapped[str] = mapped_column(Text)        # single_layer | multi_colour | multi_colour_hd | chat | summary ...
    provider: Mapped[str] = mapped_column(Text)       # 'openai'
    model: Mapped[str] = mapped_column(Text)
    quality: Mapped[Optional[str]] = mapped_column(Text)
    size: Mapped[Optional[str]] = mapped_column(Text)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 5))
    cost_inr: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3))
    credits_charged: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    status: Mapped[str] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (
        CheckConstraint("status IN ('ok','failed')", name="status_ok"),
        Index("ix_ai_calls_account_created", "account_id", "created_at"),
    )
