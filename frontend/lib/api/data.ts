// Parties, designs, chats and billing. The backend has no database yet, so by default these use
// the in-browser demo store (lib/mock/store.ts). With NEXT_PUBLIC_USE_MOCKS=0 they call the REST
// routes listed in docs/API.md instead; the screens do not change.

import { mockAuth, mockBilling, mockChats, mockDesigns, mockParties } from "../mock/store";
import { API_BASE, USE_MOCKS, jsonBody, request } from "./client";
import type {
  AiAction,
  AiContext,
  Chat,
  ChatMessage,
  CreditSummary,
  Design,
  DesignVersion,
  Invoice,
  LedgerEntry,
  Me,
  Member,
  Party,
  PartyInput,
  Plan,
  PlanId,
  Subscription,
} from "./types";

const q = (params: Record<string, string | boolean | number | undefined>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") s.set(k, String(v));
  const str = s.toString();
  return str ? `?${str}` : "";
};
const get = <T,>(path: string) => request<T>(`${API_BASE}${path}`);
const post = <T,>(path: string, body: unknown = {}) => request<T>(`${API_BASE}${path}`, jsonBody(body));
const patch = <T,>(path: string, body: unknown) =>
  request<T>(`${API_BASE}${path}`, { ...jsonBody(body), method: "PATCH" });

/** A one-time login link for a designer: /join?code=ABCDE-FGH23 (the code is also the passcode). */
export interface InviteLink {
  ok: boolean;
  invite_code: string;
  invite_path: string;
  invite_expires_at: string;
}

const demoOnly = (): Promise<never> => Promise.reject(new Error("Team invites need the real backend (NEXT_PUBLIC_USE_MOCKS=0)."));

export type GoogleAnswer =
  | { logged_in: true; me: Me }
  | { logged_in: false; signup_token: string; email: string; full_name: string };

/** Same fields as GoogleCompleteIn in backend/magic_db/schemas.py. */
export interface GoogleDetails {
  signup_token: string;
  phone: string;
  company_name: string;
  owner_name?: string | null;
  city?: string | null;
  gstin?: string | null;
}

/** Same fields as RegisterIn in backend/magic_db/schemas.py. */
export interface RegisterInput {
  phone: string;
  password: string;
  owner_name: string;
  company_name: string;
  gstin?: string | null;
  email?: string | null;
  city?: string | null;
}

// The login lives in an httpOnly cookie (mo_session) that the backend sets; the page never sees it.
export const authApi = {
  me: (): Promise<Me> => (USE_MOCKS ? mockAuth.me() : get("/me")),
  login: (phone: string, password: string): Promise<Me> =>
    USE_MOCKS ? mockAuth.me() : post("/auth/login", { phone, password }),
  register: (input: RegisterInput): Promise<Me> => (USE_MOCKS ? mockAuth.me() : post("/auth/register", input)),
  logout: () => (USE_MOCKS ? Promise.resolve({ ok: true }) : post("/auth/logout")),
  /** Is Google login on (GOOGLE_CLIENT_ID in backend/.env)? */
  googleConfig: (): Promise<{ enabled: boolean; client_id: string | null }> =>
    USE_MOCKS ? Promise.resolve({ enabled: false, client_id: null }) : get("/auth/google/config"),
  /** Step 1: a known person is logged in at once; a new person gets a signup token for step 2. */
  google: (credential: string): Promise<GoogleAnswer> => (USE_MOCKS ? demoOnly() : post("/auth/google", { credential })),
  /** Step 2 for a new person: the shop and mobile number; logs in. */
  googleComplete: (input: GoogleDetails): Promise<Me> => (USE_MOCKS ? demoOnly() : post("/auth/google/complete", input)),
  /** Who a login link is for, before it is used. */
  inviteCheck: (code: string): Promise<{ business_name: string; full_name: string | null; phone: string; expires_at: string }> =>
    USE_MOCKS ? demoOnly() : post("/auth/invite/check", { code }),
  /** Logs in with a login link; it works once. */
  inviteAccept: (code: string): Promise<Me> => (USE_MOCKS ? demoOnly() : post("/auth/invite/accept", { code })),
  updateProfile: (input: { full_name: string; business_name: string; gstin: string | null }) =>
    USE_MOCKS ? mockAuth.updateProfile(input) : patch("/me", input),
};

export const partiesApi = {
  list: (opts: { q?: string; archived?: boolean } = {}): Promise<Party[]> =>
    USE_MOCKS ? mockParties.list(opts) : get(`/parties${q(opts)}`),
  get: (id: string): Promise<Party> => (USE_MOCKS ? mockParties.get(id) : get(`/parties/${id}`)),
  create: (input: PartyInput): Promise<Party> => (USE_MOCKS ? mockParties.create(input) : post("/parties", input)),
  update: (id: string, input: Partial<PartyInput>): Promise<Party> =>
    USE_MOCKS ? mockParties.update(id, input) : patch(`/parties/${id}`, input),
  setArchived: (id: string, archived: boolean): Promise<Party> =>
    USE_MOCKS ? mockParties.setArchived(id, archived) : patch(`/parties/${id}`, { archived }),
  rebuildSummary: (id: string): Promise<Party> =>
    USE_MOCKS ? mockParties.rebuildSummary(id) : post(`/parties/${id}/summary/rebuild`),
  setReferences: (id: string, versionIds: string[]): Promise<Party> =>
    USE_MOCKS ? mockParties.setReferences(id, versionIds) : post(`/parties/${id}/references`, { version_ids: versionIds }),
};

export type NewVersion = Omit<DesignVersion, "id" | "design_id" | "created_at">;

export const designsApi = {
  list: (opts: { partyId?: string; q?: string } = {}): Promise<Design[]> =>
    USE_MOCKS ? mockDesigns.list(opts) : get(`/designs${q({ party_id: opts.partyId, q: opts.q })}`),
  get: (id: string): Promise<Design> => (USE_MOCKS ? mockDesigns.get(id) : get(`/designs/${id}`)),
  create: (input: { party_id: string | null; name: string }): Promise<Design> =>
    USE_MOCKS ? mockDesigns.create(input) : post("/designs", input),
  update: (id: string, input: { name?: string; party_id?: string | null; current_version_id?: string }): Promise<Design> =>
    USE_MOCKS ? mockDesigns.update(id, input) : patch(`/designs/${id}`, input),
  addVersion: (id: string, v: NewVersion, makeCurrent = true): Promise<DesignVersion> =>
    USE_MOCKS ? mockDesigns.addVersion(id, v, makeCurrent) : post(`/designs/${id}/versions`, { ...v, make_current: makeCurrent }),
  recordExport: (id: string, fmt: string) =>
    USE_MOCKS ? mockDesigns.recordExport(id, fmt) : post(`/designs/${id}/exports`, { format: fmt }),
  remove: (id: string) =>
    USE_MOCKS ? mockDesigns.remove(id) : request(`${API_BASE}/designs/${id}`, { method: "DELETE" }),
  /** Deletes one image of the design (and its saved layers); the design keeps the others. */
  removeVersion: (id: string, versionId: string) =>
    USE_MOCKS
      ? mockDesigns.removeVersion(id, versionId)
      : request(`${API_BASE}/designs/${id}/versions/${versionId}`, { method: "DELETE" }),
  /** Which backend image session (POST /api/sessions) belongs to this design, if it is still alive. */
  getSession: (id: string): Promise<string | null> =>
    USE_MOCKS ? mockDesigns.getSession(id) : get<{ sid: string | null }>(`/designs/${id}/session`).then((r) => r.sid),
  setSession: (id: string, sid: string | null) =>
    USE_MOCKS ? mockDesigns.setSession(id, sid) : post(`/designs/${id}/session`, { sid }),
};

export type NewMessage = Omit<ChatMessage, "id" | "chat_id" | "created_at">;

export const chatsApi = {
  list: (opts: { partyId?: string; q?: string } = {}): Promise<Chat[]> =>
    USE_MOCKS ? mockChats.list(opts) : get(`/chats${q({ party_id: opts.partyId, q: opts.q })}`),
  get: (id: string): Promise<Chat> => (USE_MOCKS ? mockChats.get(id) : get(`/chats/${id}`)),
  forDesign: (designId: string): Promise<Chat[]> =>
    USE_MOCKS ? mockChats.forDesign(designId) : get(`/chats${q({ design_id: designId })}`),
  start: (designId: string, title: string): Promise<Chat> =>
    USE_MOCKS ? mockChats.start(designId, title) : post("/chats", { design_id: designId, title }),
  addMessage: (chatId: string, m: NewMessage): Promise<ChatMessage> =>
    USE_MOCKS ? mockChats.addMessage(chatId, m) : post(`/chats/${chatId}/messages`, m),
  aiContext: (chatId: string): Promise<AiContext> =>
    USE_MOCKS ? mockChats.aiContext(chatId) : get(`/chats/${chatId}/ai-context`),
};

export interface BillingSummary {
  subscription: Subscription;
  plan: Plan;
  credits: CreditSummary;
}

export interface Reservation {
  cost: number;
  settle: (ok: boolean) => Promise<unknown>;
}

/** The frontend's AI actions, as the price list in backend/magic_db/config.py (CREDIT_COST) names them. */
const SERVER_ACTION: Record<AiAction, string> = {
  preview: "single_layer",
  final: "multi_colour",
  area_edit: "multi_colour",
  watermark: "multi_colour",                 // gpt-image-2.5-sunburst
  resize_fill: "multi_colour",
  layer_hd: "multi_colour_hd",
};

export const billingApi = {
  plans: (): Promise<Plan[]> => (USE_MOCKS ? mockBilling.plans() : get("/plans")),
  summary: (): Promise<BillingSummary> => (USE_MOCKS ? mockBilling.summary() : get("/billing")),
  usage: (): Promise<LedgerEntry[]> => (USE_MOCKS ? mockBilling.usage() : get("/billing/usage")),
  invoices: (): Promise<Invoice[]> => (USE_MOCKS ? mockBilling.invoices() : get("/billing/invoices")),
  members: (): Promise<Member[]> => (USE_MOCKS ? mockBilling.members() : get("/team")),
  /** Adds a designer with the password the owner chose, and returns a one-time login link to share. */
  invite: (phone: string, name: string, password: string): Promise<InviteLink & { temp_password?: string }> =>
    USE_MOCKS ? demoOnly() : post("/team/invite", { phone, full_name: name, password }),
  /** A new one-time login link for a designer (the old one stops working). */
  inviteLink: (userId: string): Promise<InviteLink> => (USE_MOCKS ? demoOnly() : post(`/team/${userId}/invite-link`)),
  removeMember: (userId: string) =>
    USE_MOCKS ? mockBilling.removeMember(userId) : request(`${API_BASE}/team/${userId}`, { method: "DELETE" }),
  changePlan: (planId: PlanId, period: "monthly" | "yearly") =>
    USE_MOCKS ? mockBilling.changePlan(planId, period) : post("/billing/plan", { plan_id: planId, period }),
  buyCredits: (amount: number) =>
    USE_MOCKS ? mockBilling.buyCredits(amount) : post("/billing/top-up", { credits: amount }),
  setWarnAt: (n: number) => (USE_MOCKS ? mockBilling.setWarnAt(n) : patch("/billing", { warn_at: n })),

  /**
   * Takes the credits before a paid AI call (402 when there are not enough) and gives them back
   * with settle(false) when the call fails. Demo mode does the same in the browser store.
   */
  reserve: async (
    action: AiAction,
    count: number,
    label: string,
    partyName: string | null,
    designName: string | null,
  ): Promise<Reservation> => {
    if (USE_MOCKS) return mockBilling.reserve(action, count, label, partyName, designName);
    const hold = await post<{ hold_id: string; cost: number }>("/credits/reserve", {
      action: SERVER_ACTION[action],
      count,
      label: [label, designName].filter(Boolean).join(" · "),
    });
    return { cost: hold.cost, settle: (ok: boolean) => post(`/credits/${hold.hold_id}/settle`, { ok }) };
  },

  logFree: (label: string, partyName: string | null, designName: string | null) =>
    USE_MOCKS ? mockBilling.logFree(label, partyName, designName) : Promise.resolve(),
};
