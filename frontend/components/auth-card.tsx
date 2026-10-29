"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { errorText } from "@/lib/api/client";
import { authApi } from "@/lib/api/data";
import { GoogleButton } from "./google-button";
import { Button, Field, Input } from "./ui/primitives";

const MIN_PASSWORD = 8; // PASSWORD_MIN_LENGTH in backend/magic_db/config.py

/** The page frame of the login and register screens: logo, title, one white card. */
function Frame({ title, subtitle, wide, children }: { title: string; subtitle: string; wide?: boolean; children: React.ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center bg-canvas px-4 py-6">
      <div className={wide ? "w-full max-w-lg" : "w-full max-w-sm"}>
        <div className="mb-4 flex items-center justify-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent font-bold text-white">M</span>
          <span className="text-lg font-semibold">Magic Outline</span>
        </div>
        <div className="rounded-2xl border border-line bg-surface p-6 shadow-sm">
          <h1 className="text-xl font-semibold">{title}</h1>
          <p className="mt-1 text-sm text-muted">{subtitle}</p>
          <div className="mt-4">{children}</div>
        </div>
      </div>
    </main>
  );
}

/** After login or register: forget the old account's data and open the page the user wanted. */
function useDone() {
  const router = useRouter();
  const params = useSearchParams();
  const client = useQueryClient();
  return () => {
    client.clear();
    const next = params.get("next");
    router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/workspace");
  };
}

const GOOGLE_KEY = "magic-outline-google-signup"; // step 1's answer, kept for step 2 in this tab only

/** Google: a known person goes straight in; a new person goes to step 2 (shop name and mobile). */
function useGoogle(setError: (s: string) => void) {
  const done = useDone();
  const router = useRouter();
  const params = useSearchParams();
  return async (credential: string) => {
    setError("");
    try {
      const r = await authApi.google(credential);
      if (r.logged_in) return done();
      sessionStorage.setItem(GOOGLE_KEY, JSON.stringify(r));
      const next = params.get("next");
      router.push(`/register/details${next ? `?next=${encodeURIComponent(next)}` : ""}`);
    } catch (err) {
      setError(errorText(err));
    }
  };
}

function ErrorLine({ text }: { text: string }) {
  return text ? (
    <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-danger">
      {text}
    </p>
  ) : null;
}

export function LoginCard() {
  const done = useDone();
  const params = useSearchParams();
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const google = useGoogle(setError);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await authApi.login(phone, password);
      done();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Frame title="Log in" subtitle="Welcome back. Use Google, or your mobile number and password.">
      <GoogleButton onCredential={google} />
      <form onSubmit={submit} className="space-y-4">
        <Field label="Mobile number" htmlFor="phone">
          <Input id="phone" type="tel" inputMode="tel" autoComplete="tel" placeholder="98250 12345" value={phone} onChange={(e) => setPhone(e.target.value)} required autoFocus />
        </Field>
        <Field label="Password" htmlFor="password">
          <Input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <ErrorLine text={error} />
        <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />} Log in
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-muted">
        New here?{" "}
        <Link href={`/register${params.get("next") ? `?next=${encodeURIComponent(params.get("next")!)}` : ""}`} className="font-medium text-accent-ink hover:underline">
          Create an account
        </Link>
      </p>
    </Frame>
  );
}

export function RegisterCard() {
  const done = useDone();
  const [form, setForm] = useState({ owner_name: "", company_name: "", phone: "", password: "", email: "", city: "", gstin: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  const short = form.password.length > 0 && form.password.length < MIN_PASSWORD;
  const google = useGoogle(setError);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (form.password.length < MIN_PASSWORD) return setError(`The password needs at least ${MIN_PASSWORD} characters.`);
    setError("");
    setBusy(true);
    try {
      await authApi.register({
        owner_name: form.owner_name.trim(),
        company_name: form.company_name.trim(),
        phone: form.phone,
        password: form.password,
        email: form.email.trim() || null,
        city: form.city.trim() || null,
        gstin: form.gstin.trim() || null,
      });
      done();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Frame title="Create your account" subtitle="Free trial with 100 credits. You can add more details later." wide>
      <GoogleButton onCredential={google} text="signup_with" />
      <form onSubmit={submit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Your name" htmlFor="owner_name">
          <Input id="owner_name" autoComplete="name" value={form.owner_name} onChange={set("owner_name")} required autoFocus />
        </Field>
        <Field label="Shop or company name" htmlFor="company_name">
          <Input id="company_name" autoComplete="organization" value={form.company_name} onChange={set("company_name")} required />
        </Field>
        <Field label="Mobile number" htmlFor="phone">
          <Input id="phone" type="tel" inputMode="tel" autoComplete="tel" placeholder="98250 12345" value={form.phone} onChange={set("phone")} required />
        </Field>
        <Field label="Password" htmlFor="password" error={short ? `At least ${MIN_PASSWORD} characters.` : undefined}>
          <Input id="password" type="password" autoComplete="new-password" placeholder={`At least ${MIN_PASSWORD} characters`} value={form.password} onChange={set("password")} required />
        </Field>
        </div>
        <details className="rounded-lg border border-line px-3 py-2 text-sm">
          <summary className="cursor-pointer text-muted">More details (optional)</summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Field label="Email" htmlFor="email">
              <Input id="email" type="email" autoComplete="email" value={form.email} onChange={set("email")} />
            </Field>
            <Field label="City" htmlFor="city">
              <Input id="city" autoComplete="address-level2" value={form.city} onChange={set("city")} />
            </Field>
            <Field label="GST number" htmlFor="gstin" hint="15 characters, like 24ABCDE1234F1Z5" className="sm:col-span-2">
              <Input id="gstin" value={form.gstin} onChange={set("gstin")} className="uppercase" />
            </Field>
          </div>
        </details>
        <ErrorLine text={error} />
        <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />} Create account
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-accent-ink hover:underline">
          Log in
        </Link>
      </p>
    </Frame>
  );
}

/** A designer's one-time login link (/join?code=...): shows the shop, then logs in once. */
export function JoinCard() {
  const done = useDone();
  const params = useSearchParams();
  const [code, setCode] = useState(params.get("code") ?? "");
  const [info, setInfo] = useState<{ business_name: string; full_name: string | null; phone: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function check(c: string) {
    setError("");
    setInfo(null);
    setBusy(true);
    try {
      setInfo(await authApi.inviteCheck(c));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  // opened from the link: check it at once (checking does not use it up)
  useEffect(() => {
    const c = params.get("code");
    if (c) check(c);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function join() {
    setError("");
    setBusy(true);
    try {
      await authApi.inviteAccept(code);
      done();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Frame title="Join your team" subtitle="Your shop owner sent you a login link. It works once.">
      {info ? (
        <div className="space-y-4">
          <div className="rounded-lg bg-canvas p-3 text-sm">
            <p>
              <span className="text-muted">Shop: </span>
              <b>{info.business_name}</b>
            </p>
            {info.full_name && (
              <p>
                <span className="text-muted">You: </span>
                {info.full_name}
              </p>
            )}
            <p>
              <span className="text-muted">Mobile: </span>
              {info.phone}
            </p>
          </div>
          <ErrorLine text={error} />
          <Button variant="primary" size="lg" className="w-full" onClick={join} disabled={busy}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Log in and join
          </Button>
          <p className="text-xs text-muted">Next time, log in with your mobile number and the password your owner gave you.</p>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            check(code);
          }}
          className="space-y-4"
        >
          <Field label="Passcode" htmlFor="code" hint="10 letters and numbers, like ABCDE-FGH23">
            <Input id="code" value={code} onChange={(e) => setCode(e.target.value)} className="font-mono uppercase" required autoFocus />
          </Field>
          <ErrorLine text={error} />
          <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Continue
          </Button>
        </form>
      )}
      <p className="mt-5 text-center text-sm text-muted">
        Already joined?{" "}
        <Link href="/login" className="font-medium text-accent-ink hover:underline">
          Log in
        </Link>
      </p>
    </Frame>
  );
}

/** Google step 2 for a new person: the shop name and mobile number, then straight in. */
export function GoogleDetailsCard() {
  const done = useDone();
  const [ticket, setTicket] = useState<{ signup_token: string; email: string; full_name: string } | null | undefined>(undefined);
  const [form, setForm] = useState({ owner_name: "", company_name: "", phone: "", city: "", gstin: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  useEffect(() => {
    try {
      const t = JSON.parse(sessionStorage.getItem(GOOGLE_KEY) ?? "null");
      setTicket(t);
      if (t) setForm((f) => ({ ...f, owner_name: t.full_name ?? "" }));
    } catch {
      setTicket(null);
    }
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!ticket) return;
    setError("");
    setBusy(true);
    try {
      await authApi.googleComplete({
        signup_token: ticket.signup_token,
        phone: form.phone,
        company_name: form.company_name.trim(),
        owner_name: form.owner_name.trim() || null,
        city: form.city.trim() || null,
        gstin: form.gstin.trim() || null,
      });
      sessionStorage.removeItem(GOOGLE_KEY);
      done();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  if (ticket === undefined) return null;
  if (!ticket)
    return (
      <Frame title="Sign in with Google first" subtitle="This step comes after choosing your Google account.">
        <Link href="/register" className="font-medium text-accent-ink hover:underline">
          Back to create account
        </Link>
      </Frame>
    );

  return (
    <Frame title="Almost done" subtitle={`Signed in as ${ticket.email}. Tell us about your shop.`}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Your name" htmlFor="owner_name">
          <Input id="owner_name" autoComplete="name" value={form.owner_name} onChange={set("owner_name")} required />
        </Field>
        <Field label="Shop or company name" htmlFor="company_name">
          <Input id="company_name" autoComplete="organization" value={form.company_name} onChange={set("company_name")} required autoFocus />
        </Field>
        <Field label="Mobile number" htmlFor="phone" hint="Your team and login help use this number.">
          <Input id="phone" type="tel" inputMode="tel" autoComplete="tel" placeholder="98250 12345" value={form.phone} onChange={set("phone")} required />
        </Field>
        <details className="rounded-lg border border-line px-3 py-2 text-sm">
          <summary className="cursor-pointer text-muted">More details (optional)</summary>
          <div className="mt-3 space-y-3">
            <Field label="City" htmlFor="city">
              <Input id="city" autoComplete="address-level2" value={form.city} onChange={set("city")} />
            </Field>
            <Field label="GST number" htmlFor="gstin" hint="15 characters, like 24ABCDE1234F1Z5">
              <Input id="gstin" value={form.gstin} onChange={set("gstin")} className="uppercase" />
            </Field>
          </div>
        </details>
        <ErrorLine text={error} />
        <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />} Start free trial
        </Button>
      </form>
    </Frame>
  );
}
