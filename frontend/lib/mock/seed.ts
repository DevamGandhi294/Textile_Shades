// Demo data for the parts the backend does not have yet (no database).
// Dates are relative to "now" so the lists read "Today", "2 days", ...

import type {
  Account,
  Chat,
  ChatMessage,
  Design,
  DesignVersion,
  Invoice,
  LedgerEntry,
  Member,
  Party,
  Plan,
  Subscription,
  User,
} from "../api/types";
import { demoImage, type Motif } from "./images";

export interface DemoDb {
  version: number;
  account: Account;
  users: User[];
  members: { user_id: string; role: "owner" | "designer"; joined_at: string }[];
  parties: Omit<Party, "design_count" | "chat_count" | "raw_count" | "last_activity_at">[];
  designs: Omit<Design, "chat_count" | "credits_used">[];
  chats: Omit<Chat, "result_label">[];
  ledger: LedgerEntry[];
  invoices: Invoice[];
  subscription: Subscription;
  warn_at: number;
  /** backend session per design (kept for an hour by backend/api.py) */
  sessions: Record<string, { sid: string; at: number }>;
}

export const DB_VERSION = 5; // a new number clears what the browser saved before

/** false = start empty: no demo parties, designs, chats, usage or invoices; only what you make yourself appears. */
export const DEMO_CONTENT = false;

export const PLANS: Plan[] = [
  {
    id: "starter",
    name: "Starter",
    tagline: "One designer, a few parties",
    monthly_credits: 150,
    seats: 1,
    max_parties: 20,
    price_month_inr: null,
    price_year_inr: null,
    features: ["150 credits a month", "1 user", "Up to 20 parties", "All export formats"],
  },
  {
    id: "studio",
    name: "Studio",
    tagline: "Small design studio",
    monthly_credits: 600,
    seats: 3,
    max_parties: null,
    price_month_inr: null,
    price_year_inr: null,
    features: ["600 credits a month", "3 users", "Unlimited parties", "Area selector and party memory"],
  },
  {
    id: "business",
    name: "Business",
    tagline: "Embroidery or weaving unit",
    monthly_credits: 2000,
    seats: 10,
    max_parties: null,
    price_month_inr: null,
    price_year_inr: null,
    features: ["2,000 credits a month", "10 users", "Unlimited parties", "Batch upload and priority speed"],
  },
];

export const HIDDEN_RULES = "Black outline, white background, closed shapes.";

let n = 0;
const id = (p: string) => `${p}_${(++n).toString(36).padStart(4, "0")}`;

export function makeSeed(now = new Date()): DemoDb {
  n = 0;
  const ago = (days: number, hours = 0) =>
    new Date(now.getTime() - days * 86_400_000 - hours * 3_600_000).toISOString();

  const account: Account = { id: "acc_demo", business_name: "Your business", gstin: null, created_at: ago(220) };
  const owner: User = {
    id: "usr_owner",
    phone: "+91 98250 00000",
    email: null,
    full_name: "Your name",
    created_at: ago(220),
    last_login_at: ago(0),
  };
  const designer: User = {
    id: "usr_designer",
    phone: "+91 98250 11111",
    email: null,
    full_name: "Designer name",
    created_at: ago(90),
    last_login_at: ago(2),
  };

  const party = (
    name: string,
    area: string,
    since: number,
    prefs: Partial<DemoDb["parties"][number]> = {},
  ): DemoDb["parties"][number] => ({
    id: id("pty"),
    name,
    contact_person: null,
    phone: null,
    area,
    gstin: null,
    usual_motifs: null,
    border_width: null,
    line_thickness: null,
    software: null,
    default_formats: [],
    ai_summary: null,
    ai_summary_auto: true,
    ai_summary_updated: null,
    archived: false,
    created_at: ago(since),
    reference_version_ids: [],
    ...prefs,
  });

  const shree = party("Shree Textiles", "Ring Road, Surat", 210, {
    contact_person: "Rameshbhai",
    phone: "+91 98240 12345",
    usual_motifs: "Paisley, peacock",
    border_width: "8–12 cm",
    line_thickness: "medium",
    software: "wilcom",
    default_formats: ["eps", "bmp"],
    ai_summary:
      "Saree and dupatta borders for Wilcom. Likes paisley and peacock motifs, borders 8–12 cm wide, medium even lines. Wants every shape closed so it can be filled, corners kept sharp, and the designer's own line placement kept close. Usually exports EPS for Wilcom and BMP for the CAD team.",
    ai_summary_updated: ago(8),
  });
  const laxmi = party("Laxmi Sarees", "Varachha, Surat", 150, {
    usual_motifs: "Mango buta, florals",
    border_width: "6 cm",
    line_thickness: "thin",
    software: "coreldraw",
    default_formats: ["svg"],
  });
  const om = party("Om Embroidery Works", "Udhna, Surat", 300, {
    usual_motifs: "Peacock, temple",
    line_thickness: "bold",
    software: "wilcom",
    default_formats: ["dxf", "eps"],
  });
  const radhe = party("Radhe Creation", "Sachin GIDC, Surat", 60, { software: "photoshop", default_formats: ["psd"] });
  const krishna = party("Krishna Fab", "Katargam, Surat", 120, { software: "coreldraw", default_formats: ["svg", "pdf"] });

  const designs: DemoDb["designs"] = [];
  const chats: DemoDb["chats"] = [];

  function design(
    p: { id: string },
    name: string,
    motif: Motif,
    sizeMm: [number, number],
    daysAgo: number,
    outlines: number,
    cols = 3,
    extra: Partial<DemoDb["designs"][number]> = {},
  ) {
    const did = id("dsn");
    const versions: DesignVersion[] = [];
    const add = (kind: DesignVersion["kind"], label: string, note: string | null, credits = 0, img = kind) => {
      const v: DesignVersion = {
        id: id("ver"),
        design_id: did,
        parent_id: versions.at(-1)?.id ?? null,
        kind,
        label,
        note,
        image_url: demoImage(motif, img, cols),
        width_px: kind === "raw" ? 3024 : 2400,
        height_px: kind === "raw" ? 4032 : Math.round((2400 * sizeMm[1]) / sizeMm[0]),
        dpi: kind === "outline" ? 300 : null,
        width_mm: kind === "outline" ? sizeMm[0] : null,
        height_mm: kind === "outline" ? sizeMm[1] : null,
        settings: null,
        closed_boxes: kind === "outline" ? 46 : null,
        gaps_joined: kind === "outline" ? 3 : null,
        credits,
        chat_message_id: null,
        created_at: ago(daysAgo, 3 - versions.length * 0.2),
      };
      versions.push(v);
      return v;
    };
    add("raw", "Raw", "Phone photo");
    add("scan", "Scanned", "Auto clean");
    add("ai", "AI result", "gpt-image-2 · 2 cr", 2);
    for (let i = 1; i <= outlines; i++) add("outline", `Outline v${i}`, i === 1 ? "46 boxes" : i === outlines ? "Current" : null);
    const d: DemoDb["designs"][number] = {
      id: did,
      party_id: p.id,
      name,
      current_version_id: versions.at(-1)!.id,
      created_at: ago(daysAgo),
      updated_at: ago(daysAgo),
      versions,
      last_exports: [],
      ...extra,
    };
    designs.push(d);
    return d;
  }

  function chat(
    d: DemoDb["designs"][number],
    title: string,
    daysAgo: number,
    turns: { user: string; reply: string; credits?: number; prompt?: string; versionLabel?: string }[],
  ) {
    const cid = id("cht");
    const messages: ChatMessage[] = [];
    turns.forEach((t, i) => {
      const at = ago(daysAgo, 2 - i * 0.3);
      messages.push({
        id: id("msg"),
        chat_id: cid,
        role: "user",
        content: t.user,
        attachment_version_id: null,
        final_prompt: null,
        model_label: null,
        credits_used: 0,
        created_at: at,
      });
      const v = t.versionLabel ? d.versions.find((x) => x.label === t.versionLabel) : undefined;
      messages.push({
        id: id("msg"),
        chat_id: cid,
        role: "assistant",
        content: t.reply,
        attachment_version_id: v?.id ?? null,
        final_prompt: t.prompt ?? null,
        model_label: t.credits ? `gpt-image-2 · medium · ${t.credits} credits` : null,
        credits_used: t.credits ?? 0,
        created_at: at,
      });
      if (v) v.chat_message_id = messages.at(-1)!.id;
    });
    chats.push({
      id: cid,
      party_id: d.party_id,
      design_id: d.id,
      title,
      summary: null,
      last_message_at: messages.at(-1)!.created_at,
      created_at: messages[0]!.created_at,
      messages,
    });
  }

  const paisley = design(shree, "Paisley saree border", "paisley", [80, 100], 0, 2, 2, { last_exports: ["svg", "bmp"] });
  paisley.versions.at(-1)!.note = "Mirrored · current";
  chat(paisley, "Clean the sketch", 0, [
    {
      user: "Clean this sketch. Paisley corners, keep my lines close, 8 cm wide.",
      reply: "Outline v1 is ready. 46 closed boxes, 3 gaps joined.",
      credits: 2,
      prompt:
        "Redraw this saree border sketch as clean black line art. Paisley corners. Keep every motif in place. Closed shapes, one line thickness, white background.",
      versionLabel: "Outline v1",
    },
  ]);
  chat(paisley, "Thinner and mirrored", 0, [
    {
      user: "Thinner lines and mirror the left half.",
      reply: "Outline v2 done with mirror and 70% thickness. No AI credits used.",
      versionLabel: "Outline v2",
    },
  ]);
  chat(paisley, "Lotus buds idea", 0, [
    { user: "Add small lotus buds along the middle band.", reply: "Noted. Press Generate when you want me to try it (about 2 credits)." },
  ]);

  const peacock = design(shree, "Peacock pallu corner", "peacock", [300, 200], 10, 4);
  chat(peacock, "Peacock pallu corner", 10, [
    { user: "Make the tail feathers closed boxes.", reply: "Done. Every feather is now a closed box.", credits: 2, versionLabel: "Outline v4" },
  ]);
  const mango = design(shree, "Mango buta repeat", "mango", [60, 60], 13, 1, 1);
  chat(mango, "Mango buta repeat", 13, [
    { user: "Repeat 6 cm, fill the blank space.", reply: "Outline v1 is ready. 46 closed boxes, 3 gaps joined.", credits: 2, versionLabel: "Outline v1" },
  ]);
  const temple = design(shree, "Temple border", "temple", [100, 400], 20, 3, 4);
  chat(temple, "Temple border", 20, [
    { user: "Remove the watermark in the corner.", reply: "Watermark removed.", credits: 1, versionLabel: "Outline v3" },
  ]);
  const lotus = design(shree, "Lotus dupatta border", "lotus", [70, 250], 24, 2, 3);
  chat(lotus, "Lotus dupatta border", 24, [
    { user: "Thicker outline, 120%.", reply: "Outline v2 done with 120% thickness. No AI credits used.", versionLabel: "Outline v2" },
  ]);
  const floral = design(shree, "Floral kurta neck", "floral", [150, 180], 32, 1, 2);
  chat(floral, "Floral kurta neck", 32, [
    { user: "Mirror the right side.", reply: "Mirrored the right side onto the left. No AI credits used.", versionLabel: "Outline v1" },
  ]);

  const buta = design(laxmi, "Mango buta pallu", "mango", [120, 90], 2, 1);
  chat(buta, "Mango buta pallu", 2, [
    { user: "4 previews please, thin lines.", reply: "Here are 4 low-quality previews.", credits: 4, versionLabel: "Outline v1" },
  ]);
  design(laxmi, "Floral saree border", "floral", [60, 300], 40, 2, 4);
  const omPeacock = design(om, "Peacock corner", "peacock", [200, 200], 5, 2, 2);
  chat(omPeacock, "Peacock corner", 5, [
    { user: "Change the two feathers I painted.", reply: "Both areas redrawn. Everything else stayed the same.", credits: 4, versionLabel: "Outline v2" },
  ]);
  design(om, "Temple jacquard band", "temple", [80, 350], 18, 1, 4);
  design(radhe, "Lotus neck patch", "lotus", [100, 100], 14, 1, 1);
  design(krishna, "Paisley all-over", "paisley", [250, 250], 31, 1, 3);

  // Party preferences: Shree has two favourite designs as AI references
  shree.reference_version_ids = [paisley.current_version_id!, peacock.current_version_id!];

  const periodStart = new Date(now.getFullYear(), now.getMonth(), 1);
  const periodEnd = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  const subscription: Subscription = {
    id: "sub_demo",
    plan_id: "studio",
    period: "monthly",
    status: "active",
    current_start: periodStart.toISOString(),
    current_end: periodEnd.toISOString(),
  };

  const entry = (change: number, reason: LedgerEntry["reason"], label: string, at: string, p?: string, d?: string): LedgerEntry => ({
    id: ++n,
    change,
    reason,
    label,
    party_name: p ?? null,
    design_name: d ?? null,
    created_at: at,
  });
  const ledger: LedgerEntry[] = [
    entry(600, "plan_grant", "Studio plan, monthly credits", periodStart.toISOString()),
    entry(-350, "ai_call", "Earlier usage this month", periodStart.toISOString()),
    entry(-4, "ai_call", "4 previews", ago(13), "Laxmi Sarees", "Mango buta"),
    entry(-4, "ai_call", "Area edit × 2", ago(10), "Om Embroidery", "Peacock corner"),
    entry(0, "ai_call", "Mirror + thickness", ago(0, 1), "Shree Textiles", "Paisley border"),
    entry(-2, "ai_call", "Final AI outline", ago(0, 2), "Shree Textiles", "Paisley border"),
  ];

  const invoice = (monthsAgo: number): Invoice => {
    const d = new Date(now.getFullYear(), now.getMonth() - monthsAgo, 1);
    return {
      id: id("inv"),
      invoice_no: `MO/${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, "0")}/0001`,
      label: "Studio plan",
      amount_inr: 0,
      gst_inr: 0,
      pdf_url: null,
      issued_at: d.toISOString(),
    };
  };

  return {
    version: DB_VERSION,
    account,
    users: DEMO_CONTENT ? [owner, designer] : [owner],
    members: [
      { user_id: owner.id, role: "owner", joined_at: ago(220) },
      ...(DEMO_CONTENT ? [{ user_id: designer.id, role: "designer" as const, joined_at: ago(90) }] : []),
    ],
    parties: DEMO_CONTENT ? [shree, laxmi, om, radhe, krishna] : [],
    designs: DEMO_CONTENT ? designs : [],
    chats: DEMO_CONTENT ? chats : [],
    ledger: DEMO_CONTENT ? ledger : ledger.slice(0, 1), // without demo usage: only this month's plan credits
    invoices: DEMO_CONTENT ? [invoice(0), invoice(1)] : [],
    subscription,
    warn_at: 20,
    sessions: {},
  };
}

export type { Member };
