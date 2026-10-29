"use client";

import { useMutation } from "@tanstack/react-query";
import { Copy, FileText, Link2, MessageCircle, Pencil, UserPlus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/app-shell";
import {
  Badge,
  Button,
  buttonVariants,
  Card,
  Dialog,
  DialogContent,
  ErrorBox,
  Field,
  Input,
  PendingTag,
  Segmented,
  Select,
  Skeleton,
} from "@/components/ui/primitives";
import { authApi, billingApi } from "@/lib/api/data";
import type { Plan } from "@/lib/api/types";
import { keys, useBilling, useInvoices, useMe, useMembers, usePlans, useRefreshAll, useUsage } from "@/lib/queries";
import { useQueryClient } from "@tanstack/react-query";
import { cn, initials, shortAgo, shortDate } from "@/lib/utils";

const COSTS: [string, string][] = [
  ["Preview option (low quality)", "1"],
  ["Final AI outline", "2"],
  ["Area edit, per colour", "2"],
  ["Watermark or text removal", "1"],
  ["Resize with AI fill", "2"],
  ["Thickness, gap fill, mirror, smooth, colour layers, exports", "Free"],
];

const TOP_UPS = [100, 250, 500, 1000];

/** Screen 7: profile, team seats, credits, plans, credit cost per action, usage and GST invoices. */
export default function BillingPage() {
  const billing = useBilling();
  const plans = usePlans();
  const [period, setPeriod] = useState<"monthly" | "yearly">("monthly");
  const [buyOpen, setBuyOpen] = useState(false);
  const refresh = useRefreshAll();

  useEffect(() => {
    if (billing.data) setPeriod(billing.data.subscription.period);
  }, [billing.data]);

  const change = useMutation({
    mutationFn: (p: Plan) => billingApi.changePlan(p.id, period),
    onSuccess: (_r, p) => {
      toast.success(`Switched to the ${p.name} plan.`);
      refresh();
    },
    onError: (e) => toast.error(e.message),
  });

  const warn = useMutation({
    mutationFn: (n: number) => billingApi.setWarnAt(n),
    onSuccess: () => refresh(),
  });

  const b = billing.data;
  const rank = (id: string) => ["starter", "studio", "business"].indexOf(id);

  return (
    <div>
      <PageHeader title="Account and billing" />
      <div className="space-y-6 p-4 sm:p-6">
        {billing.error && <ErrorBox error={billing.error} onRetry={() => billing.refetch()} />}
        <div className="grid gap-6 xl:grid-cols-[1fr_380px] [&>*]:min-w-0">
          <div className="space-y-6">
            <Profile />
            <Team seats={b?.plan.seats} />
          </div>

          <Card className="p-5">
            {!b ? (
              <Skeleton className="h-40" />
            ) : (
              <>
                <div className="flex items-start justify-between">
                  <p className="text-sm text-muted">Credits left</p>
                  <Badge tone="accent">{b.plan.name} plan</Badge>
                </div>
                <p className={cn("mt-1 text-5xl font-semibold tabular-nums", b.credits.balance <= b.credits.warn_at && "text-warn")}>
                  {b.credits.balance}
                </p>
                <div className="mt-4 h-2 overflow-hidden rounded-full bg-line">
                  <div
                    className="h-full rounded-full bg-accent"
                    style={{ width: `${Math.min(100, (b.credits.used_this_period / b.credits.plan_credits) * 100)}%` }}
                  />
                </div>
                <div className="mt-2 flex justify-between text-xs text-muted">
                  <span>
                    {b.credits.used_this_period} of {b.credits.plan_credits} used this month
                  </span>
                  <span>Renews {shortDate(b.subscription.current_end)}</span>
                </div>
                <div className="mt-5 flex flex-wrap items-center gap-2">
                  <Button variant="primary" onClick={() => setBuyOpen(true)}>
                    Buy extra credits
                  </Button>
                  <label className="flex items-center gap-2 text-sm text-muted">
                    Warn me at
                    <Select
                      value={b.credits.warn_at}
                      onChange={(e) => warn.mutate(Number(e.target.value))}
                      className="h-8 w-24"
                      aria-label="Warn me at"
                    >
                      {[10, 20, 50, 100].map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </Select>
                    credits
                  </label>
                </div>
              </>
            )}
          </Card>
        </div>

        <section>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Plans</h2>
            <Segmented
              value={period}
              onChange={setPeriod}
              options={[
                { value: "monthly", label: "Monthly" },
                { value: "yearly", label: "Yearly" },
              ]}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {(plans.data ?? []).map((p) => {
              const current = b?.plan.id === p.id;
              const price = period === "monthly" ? p.price_month_inr : p.price_year_inr;
              return (
                <Card key={p.id} className={cn("flex flex-col p-5", current && "border-2 border-accent")}>
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-lg font-semibold">{p.name}</p>
                      <p className="text-sm text-muted">{p.tagline}</p>
                    </div>
                    {current && <Badge tone="accent">Current</Badge>}
                  </div>
                  <p className="mt-4 text-2xl font-semibold">
                    {price == null ? <span className="text-muted">Price to be set</span> : `₹${price.toLocaleString("en-IN")}`}
                    <span className="text-sm font-normal text-muted"> / {period === "monthly" ? "month" : "year"}</span>
                  </p>
                  <ul className="mt-4 flex-1 space-y-1.5 text-sm">
                    {p.features.map((f) => (
                      <li key={f} className="flex gap-2">
                        <span className="text-accent">✓</span>
                        {f}
                      </li>
                    ))}
                  </ul>
                  <Button
                    className="mt-5"
                    variant={current ? "secondary" : rank(p.id) > rank(b?.plan.id ?? "") ? "primary" : "secondary"}
                    disabled={current || !b}
                    loading={change.isPending && change.variables?.id === p.id}
                    onClick={() => change.mutate(p)}
                  >
                    {current ? "Current plan" : rank(p.id) > rank(b?.plan.id ?? "") ? `Upgrade to ${p.name}` : `Switch to ${p.name}`}
                  </Button>
                </Card>
              );
            })}
          </div>
          <p className="mt-2 flex items-center gap-2 text-xs text-muted">
            Plan changes and payments go through Razorpay. <PendingTag />
          </p>
        </section>

        <div className="grid gap-6 xl:grid-cols-2 [&>*]:min-w-0">
          <Card className="p-5">
            <h2 className="mb-3 font-semibold">What uses credits</h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th className="pb-2 font-medium">Action</th>
                  <th className="pb-2 text-right font-medium">Credits</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {COSTS.map(([a, c]) => (
                  <tr key={a}>
                    <td className="py-2">{a}</td>
                    <td className={cn("py-2 text-right tabular-nums", c === "Free" && "text-ok")}>{c}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <div className="space-y-6">
            <RecentUsage />
            <Invoices />
          </div>
        </div>
      </div>
      <BuyCredits open={buyOpen} onOpenChange={setBuyOpen} />
    </div>
  );
}

function Profile() {
  const me = useMe();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ full_name: "", business_name: "", gstin: "" });
  const save = useMutation({
    mutationFn: () => authApi.updateProfile({ ...form, gstin: form.gstin.trim() || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.me });
      setOpen(false);
      toast.success("Profile saved.");
    },
    onError: (e) => toast.error(e.message),
  });
  const m = me.data;
  return (
    <Card className="flex items-center gap-4 p-5">
      <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-accent-soft font-semibold text-accent-ink">
        {initials(m?.user.full_name ?? "A")}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold">{m?.user.full_name ?? "–"}</p>
        <p className="truncate text-sm text-muted">
          {[m?.account.business_name, m?.user.phone, m?.role === "owner" ? "Owner" : "Designer"].filter(Boolean).join(" · ")}
        </p>
      </div>
      <Button
        size="sm"
        onClick={() => {
          setForm({ full_name: m?.user.full_name ?? "", business_name: m?.account.business_name ?? "", gstin: m?.account.gstin ?? "" });
          setOpen(true);
        }}
      >
        <Pencil className="h-3.5 w-3.5" /> Edit
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent title="Edit profile">
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate();
            }}
          >
            <Field label="Your name">
              <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
            </Field>
            <Field label="Business name">
              <Input value={form.business_name} onChange={(e) => setForm({ ...form, business_name: e.target.value })} required />
            </Field>
            <Field label="GSTIN (for GST invoices)">
              <Input value={form.gstin} onChange={(e) => setForm({ ...form, gstin: e.target.value.toUpperCase() })} />
            </Field>
            <div className="flex justify-end gap-2">
              <Button type="button" onClick={() => setOpen(false)}>Cancel</Button>
              <Button type="submit" variant="primary" loading={save.isPending}>Save</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Team({ seats }: { seats?: number }) {
  const members = useMembers();
  const refresh = useRefreshAll();
  const [open, setOpen] = useState(false);
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [share, setShare] = useState<InviteShare | null>(null);
  const invite = useMutation({
    mutationFn: () => billingApi.invite(phone, name, password),
    onSuccess: (r) => {
      setShare({ name: name.trim(), phone, password: r.temp_password ?? password, code: r.invite_code, path: r.invite_path, expires: r.invite_expires_at });
      setPhone("");
      setName("");
      setPassword("");
      refresh();
    },
    onError: (e) => toast.error(e.message),
  });
  const link = useMutation({
    mutationFn: (m: { id: string; name: string; phone: string }) => billingApi.inviteLink(m.id).then((r) => ({ r, m })),
    onSuccess: ({ r, m }) => {
      setShare({ name: m.name, phone: m.phone, password: null, code: r.invite_code, path: r.invite_path, expires: r.invite_expires_at });
      setOpen(true);
    },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => billingApi.removeMember(id),
    onSuccess: () => refresh(),
  });
  const n = members.data?.length ?? 0;
  const close = () => {
    setOpen(false);
    setShare(null);
  };
  return (
    <Card className="p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">
          Team · {n} of {seats ?? "–"} seats
        </h2>
        <Button size="sm" onClick={() => setOpen(true)}>
          <UserPlus className="h-4 w-4" /> Invite designer
        </Button>
      </div>
      {members.isLoading && (
        <div className="space-y-2 py-1">
          <Skeleton className="h-11" />
          <Skeleton className="h-11" />
        </div>
      )}
      <ul className="divide-y divide-line">
        {members.data?.map((m) => (
          <li key={m.user.id} className="flex items-center justify-between gap-3 py-2.5">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{m.user.full_name ?? m.user.phone}</p>
              <p className="text-xs text-muted">{m.user.phone}</p>
            </div>
            <div className="flex items-center gap-2">
              {m.role !== "owner" && (
                <Button
                  size="sm"
                  variant="ghost"
                  loading={link.isPending && link.variables?.id === m.user.id}
                  onClick={() => link.mutate({ id: m.user.id, name: m.user.full_name ?? "", phone: m.user.phone })}
                  title="A new one-time login link (the old one stops working)"
                >
                  <Link2 className="h-4 w-4" /> Login link
                </Button>
              )}
              <Badge tone={m.role === "owner" ? "accent" : "neutral"}>{m.role === "owner" ? "Owner" : "Designer"}</Badge>
              {m.role !== "owner" && (
                <button
                  aria-label={`Remove ${m.user.full_name ?? m.user.phone}`}
                  className="rounded p-1 text-muted hover:bg-canvas hover:text-danger"
                  onClick={() => remove.mutate(m.user.id)}
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted">All team members share the same credits and parties.</p>
      <Dialog open={open} onOpenChange={(o) => (o ? setOpen(true) : close())}>
        <DialogContent
          title={share ? "Share the login link" : "Invite designer"}
          description={share ? "The link logs them in once. After that they use their mobile number and password." : "You choose their password."}
        >
          {share ? (
            <InviteShareBox share={share} onDone={close} />
          ) : (
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                invite.mutate();
              }}
            >
              <Field label="Name">
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              <Field label="Mobile / WhatsApp">
                <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" placeholder="98250 12345" required />
              </Field>
              <Field label="Password for them" hint="At least 8 characters. They can change it later.">
                <Input value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} required />
              </Field>
              <div className="flex justify-end gap-2">
                <Button type="button" onClick={close}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary" loading={invite.isPending}>
                  Add designer
                </Button>
              </div>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

type InviteShare = { name: string; phone: string; password: string | null; code: string; path: string; expires: string };

/** The login link, its passcode and the password, ready to copy or send on WhatsApp. */
function InviteShareBox({ share, onDone }: { share: InviteShare; onDone: () => void }) {
  const url = `${window.location.origin}${share.path}`;
  const text = [
    `Hi${share.name ? ` ${share.name}` : ""}, you are invited to Magic Outline.`,
    `Open this link to log in (it works once): ${url}`,
    `Passcode: ${share.code}`,
    share.password ? `Next time log in with your mobile number and this password: ${share.password}` : "",
  ]
    .filter(Boolean)
    .join("\n");
  const digits = share.phone.replace(/\D/g, "");
  const wa = `https://wa.me/${digits.length === 10 ? `91${digits}` : digits}?text=${encodeURIComponent(text)}`;
  return (
    <div className="space-y-4">
      <div className="space-y-1 rounded-lg bg-canvas p-3 text-sm">
        <p className="break-all">
          <span className="text-muted">Link: </span>
          {url}
        </p>
        <p>
          <span className="text-muted">Passcode: </span>
          <span className="font-mono font-semibold">{share.code}</span>
        </p>
        {share.password && (
          <p>
            <span className="text-muted">Password: </span>
            <span className="font-mono">{share.password}</span>
          </p>
        )}
      </div>
      <p className="text-xs text-muted">
        The link and passcode work once, until {shortDate(share.expires)}. Anyone who opens it after that is refused. Need a
        new one? Use Login link next to the designer.
      </p>
      <div className="flex flex-wrap justify-end gap-2">
        <Button
          onClick={() => {
            navigator.clipboard?.writeText(text);
            toast.success("Copied.");
          }}
        >
          <Copy className="h-4 w-4" /> Copy
        </Button>
        <a href={wa} target="_blank" rel="noreferrer" className={buttonVariants({ variant: "secondary" })}>
          <MessageCircle className="h-4 w-4" /> Send on WhatsApp
        </a>
        <Button variant="primary" onClick={onDone}>
          Done
        </Button>
      </div>
    </div>
  );
}

function RecentUsage() {
  const usage = useUsage();
  return (
    <Card className="p-5">
      <h2 className="mb-3 font-semibold">Recent usage</h2>
      {usage.isLoading ? (
        <Skeleton className="h-24" />
      ) : usage.data?.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[420px] text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="pb-2 font-medium">Date</th>
                <th className="pb-2 font-medium">Party · design</th>
                <th className="pb-2 font-medium">Action</th>
                <th className="pb-2 text-right font-medium">Credits</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {usage.data.slice(0, 8).map((e) => (
                <tr key={e.id}>
                  <td className="py-2 text-muted">{shortAgo(e.created_at) === "Today" ? "Today" : shortDate(e.created_at)}</td>
                  <td className="py-2">{[e.party_name, e.design_name].filter(Boolean).join(" · ") || "–"}</td>
                  <td className="py-2">{e.label}</td>
                  <td className="py-2 text-right tabular-nums">{-e.change}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-muted">Nothing used yet.</p>
      )}
    </Card>
  );
}

function Invoices() {
  const invoices = useInvoices();
  return (
    <Card className="p-5">
      <h2 className="mb-3 font-semibold">Invoices</h2>
      {invoices.isLoading && <Skeleton className="h-16" />}
      {invoices.data && invoices.data.length === 0 && <p className="text-sm text-muted">No invoices yet.</p>}
      <ul className="divide-y divide-line">
        {invoices.data?.map((i) => (
          <li key={i.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
            <span>
              {new Date(i.issued_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })} · {i.label}
            </span>
            {i.pdf_url ? (
              <a href={i.pdf_url} className="flex items-center gap-1 text-accent-ink hover:underline">
                <FileText className="h-4 w-4" /> GST invoice (PDF)
              </a>
            ) : (
              <span className="flex items-center gap-2 text-muted">
                <FileText className="h-4 w-4" /> GST invoice (PDF) <PendingTag />
              </span>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-muted">Payments by UPI, card or net banking through Razorpay.</p>
    </Card>
  );
}

function BuyCredits({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [n, setN] = useState(250);
  const refresh = useRefreshAll();
  const buy = useMutation({
    mutationFn: () => billingApi.buyCredits(n),
    onSuccess: () => {
      toast.success(`${n} credits added (demo, no payment taken).`);
      refresh();
      onOpenChange(false);
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Buy extra credits" description="Extra credits are shared by the whole team.">
        <div className="grid grid-cols-2 gap-2">
          {TOP_UPS.map((v) => (
            <button
              key={v}
              onClick={() => setN(v)}
              className={cn(
                "rounded-xl border-2 p-4 text-left",
                n === v ? "border-accent bg-accent-soft" : "border-line hover:bg-canvas",
              )}
            >
              <p className="text-xl font-semibold tabular-nums">{v}</p>
              <p className="text-xs text-muted">credits · price to be set</p>
            </button>
          ))}
        </div>
        <div className="mt-5 flex items-center justify-between gap-3">
          <PendingTag />
          <div className="flex gap-2">
            <Button onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button variant="primary" onClick={() => buy.mutate()} loading={buy.isPending}>
              Pay with Razorpay
            </Button>
          </div>
        </div>
        <p className="mt-3 text-xs text-muted">
          In demo mode the credits are added without a payment. The real flow opens Razorpay Checkout and the backend confirms by webhook.
        </p>
      </DialogContent>
    </Dialog>
  );
}
