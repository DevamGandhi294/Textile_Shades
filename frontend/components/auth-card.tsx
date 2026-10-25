"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { errorText } from "@/lib/api/client";
import { authApi } from "@/lib/api/data";
import { Button, Field, Input } from "./ui/primitives";

const MIN_PASSWORD = 8; // PASSWORD_MIN_LENGTH in backend/magic_db/config.py

/** The page frame of the login and register screens: logo, title, one white card. */
function Frame({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center bg-canvas px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent font-bold text-white">M</span>
          <span className="text-lg font-semibold">Magic Outline</span>
        </div>
        <div className="rounded-2xl border border-line bg-surface p-6 shadow-sm">
          <h1 className="text-xl font-semibold">{title}</h1>
          <p className="mt-1 text-sm text-muted">{subtitle}</p>
          <div className="mt-5">{children}</div>
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
    <Frame title="Log in" subtitle="Welcome back. Use your mobile number and password.">
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
    <Frame title="Create your account" subtitle="Free trial with 100 credits. You can add more details later.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Your name" htmlFor="owner_name">
          <Input id="owner_name" autoComplete="name" value={form.owner_name} onChange={set("owner_name")} required autoFocus />
        </Field>
        <Field label="Shop or company name" htmlFor="company_name">
          <Input id="company_name" autoComplete="organization" value={form.company_name} onChange={set("company_name")} required />
        </Field>
        <Field label="Mobile number" htmlFor="phone">
          <Input id="phone" type="tel" inputMode="tel" autoComplete="tel" placeholder="98250 12345" value={form.phone} onChange={set("phone")} required />
        </Field>
        <Field label="Password" htmlFor="password" error={short ? `At least ${MIN_PASSWORD} characters.` : undefined} hint={`At least ${MIN_PASSWORD} characters.`}>
          <Input id="password" type="password" autoComplete="new-password" value={form.password} onChange={set("password")} required />
        </Field>
        <details className="rounded-lg border border-line px-3 py-2 text-sm">
          <summary className="cursor-pointer text-muted">More details (optional)</summary>
          <div className="mt-3 space-y-3">
            <Field label="Email" htmlFor="email">
              <Input id="email" type="email" autoComplete="email" value={form.email} onChange={set("email")} />
            </Field>
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
          {busy && <Loader2 className="h-4 w-4 animate-spin" />} Create account
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-accent-ink hover:underline">
          Log in
        </Link>
      </p>
    </Frame>
  );
}
