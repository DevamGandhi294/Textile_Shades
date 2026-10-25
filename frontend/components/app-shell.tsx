"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CreditCard, FolderKanban, LayoutDashboard, LogOut, MessagesSquare, Menu, Users, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, USE_MOCKS } from "@/lib/api/client";
import { authApi } from "@/lib/api/data";
import { useBilling, useMe } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { Skeleton } from "./ui/primitives";

const NAV = [
  { href: "/workspace", label: "Workspace", icon: LayoutDashboard },
  { href: "/parties", label: "Parties", icon: Users },
  { href: "/designs", label: "Designs", icon: FolderKanban },
  { href: "/chats", label: "Chats", icon: MessagesSquare },
  { href: "/billing", label: "Credits and billing", icon: CreditCard },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const me = useMe();
  const loggedOut = me.error instanceof ApiError && me.error.status === 401;
  const billing = useBilling();
  const credits = billing.data?.credits;
  const low = credits && credits.balance <= credits.warn_at;

  // not logged in: go to the login page, and come back here afterwards
  useEffect(() => {
    if (loggedOut) router.replace(`/login?next=${encodeURIComponent(path)}`);
  }, [loggedOut, path, router]);

  async function logOut() {
    try {
      await authApi.logout();
    } finally {
      client.clear(); // nothing of this account stays in the cache
      router.replace("/login");
    }
  }

  const nav = (
    <nav className="flex flex-1 flex-col gap-0.5 px-3">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = path === href || path.startsWith(href + "/");
        return (
          <Link
            key={href}
            href={href}
            onClick={() => setOpen(false)}
            className={cn(
              "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-canvas hover:text-ink",
              active && "bg-accent-soft text-accent-ink hover:bg-accent-soft hover:text-accent-ink",
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        );
      })}
    </nav>
  );

  const side = (
    <>
      <Link href="/workspace" className="flex items-center gap-2 px-6 pb-6 pt-5" onClick={() => setOpen(false)}>
        <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-sm font-bold text-white">M</span>
        <span className="font-semibold">Magic Outline</span>
      </Link>
      {nav}
      <Link
        href="/billing"
        onClick={() => setOpen(false)}
        className={cn("m-3 rounded-xl border border-line bg-canvas px-4 py-3", low && "border-amber-200 bg-amber-50")}
      >
        <p className="text-xs text-muted">Credits left</p>
        <p className={cn("text-2xl font-semibold tabular-nums", low && "text-warn")}>{credits ? credits.balance : "–"}</p>
        {USE_MOCKS && <p className="mt-1 text-[11px] text-muted">Demo data</p>}
      </Link>
      {me.data && (
        <div className="mx-3 mb-3 flex items-center gap-2 border-t border-line pt-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{me.data.user.full_name || me.data.user.phone}</p>
            <p className="truncate text-xs text-muted">{me.data.account.business_name}</p>
          </div>
          <button onClick={logOut} title="Log out" aria-label="Log out" className="rounded-md p-1.5 text-muted hover:bg-canvas hover:text-ink">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      )}
    </>
  );

  if (loggedOut || (me.isLoading && !me.data)) {
    return (
      <div className="p-6">
        <Skeleton className="h-[70vh]" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-surface lg:flex">{side}</aside>

      {/* phone and tablet: a top bar with a menu button */}
      <div className="fixed inset-x-0 top-0 z-30 flex h-12 items-center justify-between border-b border-line bg-surface px-4 lg:hidden">
        <button aria-label="Open menu" onClick={() => setOpen(true)} className="rounded-md p-1.5 hover:bg-canvas">
          <Menu className="h-5 w-5" />
        </button>
        <span className="font-semibold">Magic Outline</span>
        <Link href="/billing" className="text-sm font-medium tabular-nums text-accent-ink">
          {credits ? `${credits.balance} cr` : ""}
        </Link>
      </div>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col bg-surface">
            <button aria-label="Close menu" onClick={() => setOpen(false)} className="absolute right-3 top-4 rounded-md p-1 hover:bg-canvas">
              <X className="h-5 w-5" />
            </button>
            {side}
          </aside>
        </div>
      )}

      <main className="min-w-0 flex-1 pt-12 lg:pt-0">{children}</main>
    </div>
  );
}

export function PageHeader({
  title,
  crumbs,
  actions,
  children,
}: {
  title?: React.ReactNode;
  crumbs?: { label: string; href?: string }[];
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface px-4 py-3 sm:px-6">
      <div className="min-w-0">
        {crumbs && (
          <p className="truncate text-sm text-muted">
            {crumbs.map((c, i) => (
              <span key={i}>
                {i > 0 && <span className="mx-1.5">/</span>}
                {c.href ? (
                  <Link href={c.href} className="hover:text-ink">
                    {c.label}
                  </Link>
                ) : (
                  <span className={i === crumbs.length - 1 ? "font-medium text-ink" : ""}>{c.label}</span>
                )}
              </span>
            ))}
          </p>
        )}
        {title && <h1 className="truncate text-lg font-semibold">{title}</h1>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
