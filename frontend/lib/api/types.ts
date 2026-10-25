// Types that mirror magic_outline_schema.sql (v1). Column names are kept in snake_case so the
// real API can return rows as they are. Image fields hold a URL: a signed object-storage link
// from the real backend, or a data URL in demo mode.

export type Role = "owner" | "designer";

export interface Account {
  id: string;
  business_name: string;
  gstin: string | null;
  created_at: string;
}

export interface User {
  id: string;
  phone: string;
  email: string | null;
  full_name: string | null;
  created_at: string;
  last_login_at: string | null;
}

export interface Member {
  user: User;
  role: Role;
  joined_at: string;
}

export interface Me {
  user: User;
  account: Account;
  role: Role;
}

// ------------------------------------------------------------------ plans, credits, billing

export type PlanId = "starter" | "studio" | "business";

export interface Plan {
  id: PlanId;
  name: string;
  tagline: string;
  monthly_credits: number;
  seats: number;
  max_parties: number | null;
  price_month_inr: number | null; // null = price not set yet
  price_year_inr: number | null;
  features: string[];
}

export interface Subscription {
  id: string;
  plan_id: PlanId;
  period: "monthly" | "yearly";
  status: "active" | "past_due" | "cancelled";
  current_start: string;
  current_end: string;
}

export type LedgerReason = "plan_grant" | "top_up" | "ai_call" | "refund" | "manual_adjust" | "expiry";

export interface LedgerEntry {
  id: number;
  change: number;
  reason: LedgerReason;
  label: string; // "Final AI outline", "Mirror + thickness"
  party_name: string | null;
  design_name: string | null;
  created_at: string;
}

export interface CreditSummary {
  balance: number;
  used_this_period: number;
  plan_credits: number;
  warn_at: number;
}

export interface Invoice {
  id: string;
  invoice_no: string;
  label: string;
  amount_inr: number;
  gst_inr: number;
  pdf_url: string | null;
  issued_at: string;
}

export type AiAction = "preview" | "final" | "area_edit" | "watermark" | "resize_fill";

/** Credits per action (Account and billing → "What uses credits"). */
export const CREDIT_COST: Record<AiAction, number> = {
  preview: 1,
  final: 2,
  area_edit: 2,
  watermark: 1,
  resize_fill: 2,
};

// ------------------------------------------------------------------ parties

export type LineThickness = "thin" | "medium" | "bold";

export interface Party {
  id: string;
  name: string;
  contact_person: string | null;
  phone: string | null;
  area: string | null;
  gstin: string | null;
  usual_motifs: string | null;
  border_width: string | null;
  line_thickness: LineThickness | null;
  software: string | null;
  default_formats: string[];
  ai_summary: string | null;
  ai_summary_auto: boolean;
  ai_summary_updated: string | null;
  archived: boolean;
  created_at: string;
  // counts and last activity, joined by the API
  design_count: number;
  chat_count: number;
  raw_count: number;
  last_activity_at: string;
  reference_version_ids: string[]; // up to 4, in position order
}

export type PartyInput = Pick<
  Party,
  | "name"
  | "contact_person"
  | "phone"
  | "area"
  | "gstin"
  | "usual_motifs"
  | "border_width"
  | "line_thickness"
  | "software"
  | "default_formats"
  | "ai_summary"
  | "ai_summary_auto"
>;

// ------------------------------------------------------------------ designs

export type VersionKind = "raw" | "scan" | "ai" | "outline";

export interface DesignVersion {
  id: string;
  design_id: string;
  parent_id: string | null;
  kind: VersionKind;
  label: string; // "Raw", "Scanned", "AI result", "Outline v2"
  note: string | null; // "Phone photo", "gpt-image-2 · 2 cr", "Mirrored"
  image_url: string;
  width_px: number | null;
  height_px: number | null;
  dpi: number | null;
  width_mm: number | null;
  height_mm: number | null;
  settings: Record<string, unknown> | null;
  closed_boxes: number | null;
  gaps_joined: number | null;
  credits: number;
  chat_message_id: string | null;
  created_at: string;
}

export interface Design {
  id: string;
  party_id: string | null;
  name: string;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
  versions: DesignVersion[];
  chat_count: number;
  credits_used: number;
  last_exports: string[];
}

export type ExportFormat =
  | "svg"
  | "eps"
  | "pdf"
  | "dxf"
  | "png"
  | "tiff"
  | "bmp"
  | "zip"
  | "perfect"
  | "perfect-psd"
  | "layers-psd"
  | "layers-svg"
  | "layers-zip"
  | "ai-layers-psd";

// ------------------------------------------------------------------ chats

export interface ChatMessage {
  id: string;
  chat_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  attachment_version_id: string | null;
  final_prompt: string | null;
  model_label: string | null; // "gpt-image-2 · medium · 2 credits"
  credits_used: number;
  created_at: string;
}

export interface Chat {
  id: string;
  party_id: string | null;
  design_id: string | null;
  title: string;
  summary: string | null;
  last_message_at: string;
  created_at: string;
  messages: ChatMessage[];
  result_label: string; // "Made AI result, Outline v1 · 2 credits"
}

/** What one AI request will contain (Chats → "What AI will see"). */
export interface AiContext {
  hidden_rules: string;
  party_summary: string | null;
  chat_summary: string | null;
  last_messages: number;
  current_image: string | null;
}

// ------------------------------------------------------------------ area selector

export interface AreaSelection {
  id: string;
  color: string; // '#2563EB'
  prompt: string;
  mask_data_url: string | null;
}
