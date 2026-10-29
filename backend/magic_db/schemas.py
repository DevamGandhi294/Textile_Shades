"""Request bodies (what the frontend sends). Shapes follow frontend/lib/api/types.ts."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class OtpSendIn(BaseModel):
    phone: str


class OtpVerifyIn(BaseModel):
    phone: str
    code: str
    full_name: Optional[str] = None        # used on first login only
    business_name: Optional[str] = None


class RegisterIn(BaseModel):
    phone: str                                                       # +91XXXXXXXXXX
    password: str = Field(..., max_length=200)
    owner_name: str = Field(..., min_length=1, max_length=120)
    company_name: str = Field(..., min_length=1, max_length=200)
    gstin: Optional[str] = None                                      # optional, format checked
    email: Optional[str] = None
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: Optional[str] = None


class LoginIn(BaseModel):
    phone: str
    password: str = Field(..., max_length=200)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(..., max_length=200)
    new_password: str = Field(..., max_length=200)


class PasswordResetIn(BaseModel):
    phone: str
    code: str                                                        # OTP from /auth/password/reset/request
    new_password: str = Field(..., max_length=200)


class MeIn(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    business_name: Optional[str] = None                              # owner only, from here down
    gstin: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None


class PartyIn(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    area: Optional[str] = None
    gstin: Optional[str] = None
    usual_motifs: Optional[str] = None
    border_width: Optional[str] = None
    line_thickness: Optional[Literal["thin", "medium", "bold"]] = None
    software: Optional[str] = None
    default_formats: Optional[List[str]] = None
    ai_summary: Optional[str] = None
    ai_summary_auto: Optional[bool] = None
    archived: Optional[bool] = None


class ReferencesIn(BaseModel):
    version_ids: List[str] = Field(default_factory=list, max_length=4)


class DesignIn(BaseModel):
    party_id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=200)


class DesignPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    party_id: Optional[str] = None
    current_version_id: Optional[str] = None


class VersionIn(BaseModel):
    parent_id: Optional[str] = None
    kind: Literal["raw", "scan", "ai", "outline"]
    label: str = ""
    note: Optional[str] = None
    image_url: str                          # data:image/...;base64,... or one of our own file links
    width_px: Optional[int] = None
    height_px: Optional[int] = None
    dpi: Optional[int] = Field(None, ge=72, le=1200)
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    settings: Optional[Dict[str, Any]] = None
    closed_boxes: Optional[int] = None
    gaps_joined: Optional[int] = None
    credits: int = 0
    chat_message_id: Optional[str] = None
    make_current: bool = True


class ExportIn(BaseModel):
    format: str = Field(..., min_length=1, max_length=20)


class SessionIn(BaseModel):
    sid: Optional[str] = None


class LayerIn(BaseModel):
    color: str
    name: str
    visible: bool = True


class LayersIn(BaseModel):
    layers: List[LayerIn] = Field(default_factory=list, max_length=64)


class ChatIn(BaseModel):
    design_id: str
    title: str = ""


class MessageIn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., max_length=20000)
    attachment_version_id: Optional[str] = None
    final_prompt: Optional[str] = None
    model_label: Optional[str] = None
    credits_used: int = 0


class BillingPatch(BaseModel):
    warn_at: int = Field(..., ge=0, le=100000)


class PlanChangeIn(BaseModel):
    plan_id: str
    period: Literal["monthly", "yearly"] = "monthly"


class TopUpIn(BaseModel):
    credits: int = Field(..., gt=0)


class InviteIn(BaseModel):
    phone: str
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, max_length=200)           # set by the owner; empty = a temporary one


class GoogleIn(BaseModel):
    credential: str = Field(..., max_length=5000)                   # the ID token from the Google button


class GoogleCompleteIn(BaseModel):
    signup_token: str = Field(..., max_length=3000)                 # from POST /auth/google
    phone: str
    company_name: str = Field(..., min_length=1, max_length=200)
    owner_name: Optional[str] = Field(None, max_length=120)
    city: Optional[str] = Field(None, max_length=100)
    gstin: Optional[str] = None


class InviteCodeIn(BaseModel):
    code: str = Field(..., max_length=40)                           # from the login link, e.g. ABCDE-FGH23


class ReserveIn(BaseModel):
    action: str                             # single_layer | multi_colour | multi_colour_hd | chat
    design_id: Optional[str] = None
    label: Optional[str] = None
    count: int = Field(1, ge=1, le=20)


class SettleIn(BaseModel):
    ok: bool
