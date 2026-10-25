// In-browser demo database. It stands in for the PostgreSQL API until the backend has it,
// and is saved to localStorage so a refresh keeps your work (best effort: big images may not fit).

import { ApiError } from "../api/client";
import {
  CREDIT_COST,
  type AiAction,
  type AiContext,
  type Chat,
  type ChatMessage,
  type CreditSummary,
  type Design,
  type DesignVersion,
  type Invoice,
  type LedgerEntry,
  type Me,
  type Member,
  type Party,
  type PartyInput,
  type Plan,
  type PlanId,
  type Subscription,
} from "../api/types";
import { sleep, uid } from "../utils";
import { DB_VERSION, HIDDEN_RULES, PLANS, makeSeed, type DemoDb } from "./seed";

const KEY = "magic-outline-demo";

let db: DemoDb | null = null;

function load(): DemoDb {
  if (db) return db;
  if (typeof window !== "undefined") {
    try {
      const raw = window.localStorage.getItem(KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as DemoDb;
        if (parsed.version === DB_VERSION) return (db = parsed);
      }
    } catch {
      /* storage blocked or broken: start fresh */
    }
  }
  return (db = makeSeed());
}

function save() {
  if (!db || typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(db));
  } catch {
    // Probably over the storage quota because of uploaded images: keep the data, drop big images.
    try {
      const slim: DemoDb = JSON.parse(JSON.stringify(db));
      for (const d of slim.designs)
        for (const v of d.versions) if (v.image_url.length > 200_000 && v.image_url.startsWith("data:image/png")) v.image_url = "";
      window.localStorage.setItem(KEY, JSON.stringify(slim));
    } catch {
      /* give up quietly: the data still lives in memory for this tab */
    }
  }
}

/** Every demo call waits a little, so loading states show like they will with the real API. */
async function tx<T>(fn: (d: DemoDb) => T, ms = 180): Promise<T> {
  await sleep(ms);
  const d = load();
  const out = fn(d);
  save();
  return structuredClone(out);
}

function notFound(what: string): never {
  throw new ApiError(404, `${what} not found.`);
}

export function resetDemo() {
  db = makeSeed();
  save();
}

// ------------------------------------------------------------------ joins

function partyView(d: DemoDb, p: DemoDb["parties"][number]): Party {
  const designs = d.designs.filter((x) => x.party_id === p.id);
  const chats = d.chats.filter((x) => x.party_id === p.id);
  const last = [p.created_at, ...designs.map((x) => x.updated_at), ...chats.map((x) => x.last_message_at)].sort().at(-1)!;
  return {
    ...p,
    design_count: designs.length,
    chat_count: chats.length,
    raw_count: designs.reduce((n, x) => n + x.versions.filter((v) => v.kind === "raw").length, 0),
    last_activity_at: last,
  };
}

function designView(d: DemoDb, x: DemoDb["designs"][number]): Design {
  const chats = d.chats.filter((c) => c.design_id === x.id);
  return {
    ...x,
    chat_count: chats.length,
    credits_used: chats.reduce((n, c) => n + c.messages.reduce((m, msg) => m + msg.credits_used, 0), 0),
  };
}

function chatView(d: DemoDb, c: DemoDb["chats"][number]): Chat {
  const design = d.designs.find((x) => x.id === c.design_id);
  const made = c.messages
    .map((m) => design?.versions.find((v) => v.id === m.attachment_version_id)?.label)
    .filter(Boolean) as string[];
  const credits = c.messages.reduce((n, m) => n + m.credits_used, 0);
  return {
    ...c,
    result_label: `${made.length ? `Made ${made.join(", ")}` : "Made nothing yet"} · ${credits} credit${credits === 1 ? "" : "s"}`,
  };
}

function balance(d: DemoDb) {
  return d.ledger.reduce((n, e) => n + e.change, 0);
}

// ------------------------------------------------------------------ auth

// Login is skipped for now: the app always runs as the account owner.
export const mockAuth = {
  me: () =>
    tx((d): Me => {
      const user = d.users.find((u) => u.id === "usr_owner")!;
      return { user, account: d.account, role: "owner" };
    }, 0),

  updateProfile: (input: { full_name: string; business_name: string; gstin: string | null }) =>
    tx((d) => {
      const u = d.users.find((x) => x.id === "usr_owner");
      if (u) u.full_name = input.full_name;
      d.account.business_name = input.business_name;
      d.account.gstin = input.gstin;
      return { ok: true };
    }),
};

// ------------------------------------------------------------------ parties

export const mockParties = {
  list: (opts: { q?: string; archived?: boolean } = {}) =>
    tx((d) => {
      const q = opts.q?.trim().toLowerCase();
      return d.parties
        .filter((p) => p.archived === !!opts.archived)
        .filter((p) => !q || `${p.name} ${p.area ?? ""}`.toLowerCase().includes(q))
        .map((p) => partyView(d, p))
        .sort((a, b) => b.last_activity_at.localeCompare(a.last_activity_at));
    }),

  get: (pid: string) =>
    tx((d) => {
      const p = d.parties.find((x) => x.id === pid) ?? notFound("Party");
      return partyView(d, p);
    }),

  create: (input: PartyInput) =>
    tx((d) => {
      if (d.parties.some((p) => p.name.toLowerCase() === input.name.trim().toLowerCase()))
        throw new ApiError(422, "A party with this name already exists.");
      const plan = PLANS.find((x) => x.id === d.subscription.plan_id)!;
      if (plan.max_parties && d.parties.filter((p) => !p.archived).length >= plan.max_parties)
        throw new ApiError(402, `Your ${plan.name} plan allows ${plan.max_parties} parties. Upgrade for unlimited parties.`);
      const p: DemoDb["parties"][number] = {
        id: uid(),
        ...input,
        name: input.name.trim(),
        ai_summary_updated: input.ai_summary ? new Date().toISOString() : null,
        archived: false,
        created_at: new Date().toISOString(),
        reference_version_ids: [],
      };
      d.parties.push(p);
      return partyView(d, p);
    }),

  update: (pid: string, input: Partial<PartyInput>) =>
    tx((d) => {
      const p = d.parties.find((x) => x.id === pid) ?? notFound("Party");
      if (input.ai_summary !== undefined && input.ai_summary !== p.ai_summary) p.ai_summary_updated = new Date().toISOString();
      Object.assign(p, input);
      return partyView(d, p);
    }),

  setArchived: (pid: string, archived: boolean) =>
    tx((d) => {
      const p = d.parties.find((x) => x.id === pid) ?? notFound("Party");
      p.archived = archived;
      return partyView(d, p);
    }),

  /** Demo: builds the ~60-word summary from the party card and its chats (the real one uses the text model). */
  rebuildSummary: (pid: string) =>
    tx((d) => {
      const p = d.parties.find((x) => x.id === pid) ?? notFound("Party");
      const asks = d.chats
        .filter((c) => c.party_id === pid)
        .flatMap((c) => c.messages.filter((m) => m.role === "user").map((m) => m.content.replace(/\.$/, "")))
        .slice(0, 4);
      const bits = [
        p.usual_motifs && `Likes ${p.usual_motifs.toLowerCase()}`,
        p.border_width && `borders ${p.border_width}`,
        p.line_thickness && `${p.line_thickness} lines`,
        p.software && `works in ${p.software}`,
        p.default_formats.length && `exports ${p.default_formats.join(" + ").toUpperCase()}`,
      ].filter(Boolean);
      const text = [bits.join(", "), asks.length ? `Often asks: ${asks.join("; ")}` : ""].filter(Boolean).join(". ");
      p.ai_summary = (text || "New party, no history yet.").split(/\s+/).slice(0, 60).join(" ") + ".";
      p.ai_summary_updated = new Date().toISOString();
      return partyView(d, p);
    }, 900),

  setReferences: (pid: string, versionIds: string[]) =>
    tx((d) => {
      const p = d.parties.find((x) => x.id === pid) ?? notFound("Party");
      p.reference_version_ids = versionIds.slice(0, 4);
      return partyView(d, p);
    }),
};

// ------------------------------------------------------------------ designs

export const mockDesigns = {
  list: (opts: { partyId?: string; q?: string } = {}) =>
    tx((d) => {
      const q = opts.q?.trim().toLowerCase();
      return d.designs
        .filter((x) => !opts.partyId || x.party_id === opts.partyId)
        .filter((x) => !q || x.name.toLowerCase().includes(q))
        .map((x) => designView(d, x))
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    }),

  get: (did: string) =>
    tx((d) => designView(d, d.designs.find((x) => x.id === did) ?? notFound("Design"))),

  create: (input: { party_id: string | null; name: string }) =>
    tx((d) => {
      const now = new Date().toISOString();
      const x: DemoDb["designs"][number] = {
        id: uid(),
        party_id: input.party_id,
        name: input.name.trim() || "Untitled design",
        current_version_id: null,
        created_at: now,
        updated_at: now,
        versions: [],
        last_exports: [],
      };
      d.designs.push(x);
      return designView(d, x);
    }),

  update: (did: string, input: { name?: string; party_id?: string | null; current_version_id?: string }) =>
    tx((d) => {
      const x = d.designs.find((y) => y.id === did) ?? notFound("Design");
      Object.assign(x, input, { updated_at: new Date().toISOString() });
      return designView(d, x);
    }),

  addVersion: (did: string, v: Omit<DesignVersion, "id" | "design_id" | "created_at">, makeCurrent = true) =>
    tx((d) => {
      const x = d.designs.find((y) => y.id === did) ?? notFound("Design");
      const version: DesignVersion = { ...v, id: uid(), design_id: did, created_at: new Date().toISOString() };
      x.versions.push(version);
      if (makeCurrent) x.current_version_id = version.id;
      x.updated_at = version.created_at;
      return version;
    }, 60),

  recordExport: (did: string, fmt: string) =>
    tx((d) => {
      const x = d.designs.find((y) => y.id === did);
      if (x) x.last_exports = [fmt, ...x.last_exports.filter((f) => f !== fmt)].slice(0, 3);
      return { ok: true };
    }, 0),

  remove: (did: string) =>
    tx((d) => {
      d.designs = d.designs.filter((x) => x.id !== did);
      d.chats = d.chats.filter((c) => c.design_id !== did); // chats.design_id ON DELETE CASCADE
      return { ok: true };
    }),

  // backend/api.py keeps an uploaded photo for an hour; remember which session belongs to which design
  getSession: (did: string) =>
    tx((d) => {
      const s = d.sessions[did];
      return s && Date.now() - s.at < 55 * 60_000 ? s.sid : null;
    }, 0),

  setSession: (did: string, sid: string | null) =>
    tx((d) => {
      if (sid) d.sessions[did] = { sid, at: Date.now() };
      else delete d.sessions[did];
      return { ok: true };
    }, 0),
};

// ------------------------------------------------------------------ chats

export const mockChats = {
  list: (opts: { partyId?: string; q?: string } = {}) =>
    tx((d) => {
      const q = opts.q?.trim().toLowerCase();
      return d.chats
        .filter((c) => !opts.partyId || c.party_id === opts.partyId)
        .filter((c) => !q || `${c.title} ${c.messages.map((m) => m.content).join(" ")}`.toLowerCase().includes(q))
        .map((c) => chatView(d, c))
        .sort((a, b) => b.last_message_at.localeCompare(a.last_message_at));
    }),

  get: (cid: string) => tx((d) => chatView(d, d.chats.find((c) => c.id === cid) ?? notFound("Chat"))),

  forDesign: (did: string) =>
    tx((d) =>
      d.chats
        .filter((c) => c.design_id === did)
        .map((c) => chatView(d, c))
        .sort((a, b) => a.created_at.localeCompare(b.created_at)),
    ),

  start: (did: string, title: string) =>
    tx((d) => {
      const x = d.designs.find((y) => y.id === did) ?? notFound("Design");
      const now = new Date().toISOString();
      const c: DemoDb["chats"][number] = {
        id: uid(),
        party_id: x.party_id,
        design_id: did,
        title: title.slice(0, 60),
        summary: null,
        last_message_at: now,
        created_at: now,
        messages: [],
      };
      d.chats.push(c);
      return chatView(d, c);
    }, 0),

  addMessage: (cid: string, m: Omit<ChatMessage, "id" | "chat_id" | "created_at">) =>
    tx((d) => {
      const c = d.chats.find((x) => x.id === cid) ?? notFound("Chat");
      const msg: ChatMessage = { ...m, id: uid(), chat_id: cid, created_at: new Date().toISOString() };
      c.messages.push(msg);
      c.last_message_at = msg.created_at;
      if (m.attachment_version_id) {
        const v = d.designs.flatMap((x) => x.versions).find((x) => x.id === m.attachment_version_id);
        if (v) v.chat_message_id = msg.id;
      }
      return msg;
    }, 0),

  /** "What AI will see" for the next message of this chat. */
  aiContext: (cid: string) =>
    tx((d): AiContext => {
      const c = d.chats.find((x) => x.id === cid) ?? notFound("Chat");
      const p = d.parties.find((x) => x.id === c.party_id);
      const x = d.designs.find((y) => y.id === c.design_id);
      const current = x?.versions.find((v) => v.id === x.current_version_id);
      const older = c.messages.length > 6 ? c.messages.slice(0, -6) : [];
      return {
        hidden_rules: HIDDEN_RULES,
        party_summary: p?.ai_summary ?? null,
        chat_summary:
          c.summary ?? (older.length ? `${older.length} older messages, summarised.` : "Older messages of this design, summarised."),
        last_messages: Math.min(6, c.messages.length),
        current_image: current?.label ?? null,
      };
    }, 0),
};

// ------------------------------------------------------------------ billing

export const mockBilling = {
  plans: (): Promise<Plan[]> => tx(() => PLANS, 0),

  summary: () =>
    tx((d): { subscription: Subscription; plan: Plan; credits: CreditSummary } => {
      const plan = PLANS.find((x) => x.id === d.subscription.plan_id)!;
      const used = -d.ledger
        .filter((e) => e.created_at >= d.subscription.current_start && e.change < 0)
        .reduce((n, e) => n + e.change, 0);
      return {
        subscription: d.subscription,
        plan,
        credits: { balance: balance(d), used_this_period: used, plan_credits: plan.monthly_credits, warn_at: d.warn_at },
      };
    }, 60),

  usage: (limit = 20): Promise<LedgerEntry[]> =>
    tx((d) => d.ledger.filter((e) => e.reason === "ai_call" && e.label !== "Earlier usage this month").slice(-limit).reverse()),

  invoices: (): Promise<Invoice[]> => tx((d) => d.invoices),

  members: (): Promise<Member[]> =>
    tx((d) =>
      d.members.map((m) => ({ user: d.users.find((u) => u.id === m.user_id)!, role: m.role, joined_at: m.joined_at })),
    ),

  invite: (phone: string, name: string) =>
    tx((d) => {
      const plan = PLANS.find((x) => x.id === d.subscription.plan_id)!;
      if (d.members.length >= plan.seats) throw new ApiError(402, `All ${plan.seats} seats are used. Upgrade for more seats.`);
      const u = { id: uid(), phone, email: null, full_name: name || null, created_at: new Date().toISOString(), last_login_at: null };
      d.users.push(u);
      d.members.push({ user_id: u.id, role: "designer", joined_at: u.created_at });
      return { ok: true };
    }),

  removeMember: (userId: string) =>
    tx((d) => {
      d.members = d.members.filter((m) => m.user_id !== userId || m.role === "owner");
      return { ok: true };
    }),

  changePlan: (planId: PlanId, period: "monthly" | "yearly") =>
    tx((d) => {
      d.subscription.plan_id = planId;
      d.subscription.period = period;
      return { ok: true };
    }, 600),

  buyCredits: (amount: number) =>
    tx((d) => {
      d.ledger.push({
        id: Date.now(),
        change: amount,
        reason: "top_up",
        label: `Bought ${amount} credits`,
        party_name: null,
        design_name: null,
        created_at: new Date().toISOString(),
      });
      return { balance: balance(d) };
    }, 800),

  setWarnAt: (n: number) =>
    tx((d) => {
      d.warn_at = n;
      return { ok: true };
    }, 0),

  /**
   * Reserve credits before a paid call. Returns a function to call on success (keeps the charge)
   * or failure (gives the credits back): "credits are deducted only on success".
   */
  async reserve(action: AiAction, count: number, label: string, partyName: string | null, designName: string | null) {
    const cost = CREDIT_COST[action] * count;
    const entryId = await tx((d) => {
      if (balance(d) < cost) throw new ApiError(402, `This needs ${cost} credits and you have ${balance(d)} left.`);
      const e: LedgerEntry = {
        id: Date.now() + Math.random(),
        change: -cost,
        reason: "ai_call",
        label,
        party_name: partyName,
        design_name: designName,
        created_at: new Date().toISOString(),
      };
      d.ledger.push(e);
      return e.id;
    }, 0);
    return {
      cost,
      settle: (ok: boolean) =>
        tx((d) => {
          if (!ok) d.ledger = d.ledger.filter((e) => e.id !== entryId);
          return { ok: true };
        }, 0),
    };
  },

  /** Free actions (settings, exports) still show in "Recent usage" with 0 credits. */
  logFree: (label: string, partyName: string | null, designName: string | null) =>
    tx((d) => {
      d.ledger.push({
        id: Date.now() + Math.random(),
        change: 0,
        reason: "ai_call",
        label,
        party_name: partyName,
        design_name: designName,
        created_at: new Date().toISOString(),
      });
      return { ok: true };
    }, 0),
};
