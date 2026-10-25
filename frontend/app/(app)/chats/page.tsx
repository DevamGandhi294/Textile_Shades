"use client";

import { Check, Minus, Search } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ChatListItem, MessageBubble } from "@/components/chat-list";
import { Empty, ErrorBox, Input, Select, Skeleton, buttonVariants } from "@/components/ui/primitives";
import { useAiContext, useChat, useChats, useDesign, useParties, useParty } from "@/lib/queries";
import { cn, longDate } from "@/lib/utils";

export default function ChatsPage() {
  return (
    <Suspense>
      <ChatsView />
    </Suspense>
  );
}

/** Screen 6: one list of chats (same as a party's Chats tab), filtered by party. */
function ChatsView() {
  const router = useRouter();
  const params = useSearchParams();
  const partyId = params.get("party") ?? "";
  const [q, setQ] = useState("");
  const parties = useParties();
  const chats = useChats({ partyId: partyId || undefined, q });
  const chatId = params.get("chat") ?? chats.data?.[0]?.id ?? null;

  const link = (cid: string) => `/chats?${new URLSearchParams({ ...(partyId ? { party: partyId } : {}), chat: cid })}`;

  return (
    <div className="flex min-h-[calc(100vh-48px)] flex-col lg:h-screen lg:min-h-0 lg:flex-row">
      <section className={cn(
          "w-full shrink-0 flex-col border-b border-line bg-surface lg:flex lg:w-80 lg:border-b-0 lg:border-r",
          params.get("chat") ? "hidden" : "flex",
        )}>
        <div className="px-4 pb-2 pt-4">
          <h1 className="text-lg font-semibold">Chats</h1>
          <p className="text-xs text-muted">Same list as a party&apos;s Chats tab, filtered by party.</p>
        </div>
        <div className="space-y-2 px-4 pb-3">
          <Select
            aria-label="Party"
            value={partyId}
            onChange={(e) => router.push(e.target.value ? `/chats?party=${e.target.value}` : "/chats")}
          >
            <option value="">All parties</option>
            {parties.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search messages" className="pl-9" />
          </div>
        </div>
        <div className="max-h-[50vh] flex-1 divide-y divide-line overflow-y-auto lg:max-h-none">
          {chats.isLoading && <Skeleton className="mx-4 h-16" />}
          {chats.error && <div className="px-4"><ErrorBox error={chats.error} /></div>}
          {chats.data?.map((c) => <ChatListItem key={c.id} chat={c} href={link(c.id)} active={c.id === chatId} />)}
          {chats.data?.length === 0 && <p className="px-4 py-6 text-sm text-muted">No chats found.</p>}
        </div>
      </section>

      {chatId ? <OpenChat chatId={chatId} backHref={partyId ? `/chats?party=${partyId}` : "/chats"} /> : (
        <div className="flex-1 p-6">
          {!chats.isLoading && <Empty title="No chat selected">Chats are made in the workspace when you ask for a change.</Empty>}
        </div>
      )}
    </div>
  );
}

function OpenChat({ chatId, backHref }: { chatId: string; backHref: string }) {
  const chat = useChat(chatId);
  const design = useDesign(chat.data?.design_id);
  const party = useParty(chat.data?.party_id);
  const ctx = useAiContext(chatId);

  if (chat.isLoading) return <div className="flex-1 p-6"><Skeleton className="h-64" /></div>;
  if (chat.error) return <div className="flex-1 p-6"><ErrorBox error={chat.error} /></div>;
  const c = chat.data!;
  const versionsMade = c.messages.filter((m) => m.attachment_version_id).length;
  const byId = new Map(design.data?.versions.map((v) => [v.id, v]));

  return (
    <>
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <Link href={backHref} className="text-sm text-muted hover:text-ink lg:hidden">← Chats</Link>
            <h2 className="truncate text-lg font-semibold">{design.data?.name ?? c.title}</h2>
            <p className="text-sm text-muted">
              {[party.data?.name, `${c.messages.length} messages`, `${versionsMade} versions made`].filter(Boolean).join(" · ")}
            </p>
          </div>
          {c.design_id && (
            <div className="flex gap-2">
              <Link href={`/designs/${c.design_id}`} className={buttonVariants({ size: "sm" })}>View design</Link>
              <Link href={`/workspace/${c.design_id}?chat=${c.id}`} className={buttonVariants({ size: "sm", variant: "primary" })}>
                Continue in workspace
              </Link>
            </div>
          )}
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-6 sm:px-6">
          <p className="text-center text-xs text-muted">{longDate(c.created_at)}</p>
          {c.messages.map((m) => (
            <MessageBubble key={m.id} m={m} version={m.attachment_version_id ? byId.get(m.attachment_version_id) : null} />
          ))}
        </div>
      </section>

      <aside className="w-full shrink-0 border-t border-line bg-surface p-5 lg:w-80 lg:overflow-y-auto lg:border-l lg:border-t-0">
        <h3 className="font-semibold">What AI will see</h3>
        <p className="mt-1 text-sm text-muted">
          Only a small, fixed context is sent, so a party with hundreds of chats costs the same as a new one.
        </p>
        <ul className="mt-5 space-y-4">
          <CtxRow on title="Hidden rules" detail={ctx.data?.hidden_rules} />
          <CtxRow on={!!ctx.data?.party_summary} title="Party summary" detail="About 60 words, from the party card." />
          <CtxRow on title="Chat summary" detail="Older messages of this design, summarised." />
          <CtxRow on title={`Last ${ctx.data?.last_messages ?? 6} messages`} detail="Sent word for word." />
          <CtxRow on title="Current image" detail={`Only the latest outline or raw image${ctx.data?.current_image ? ` (${ctx.data.current_image})` : ""}.`} />
          <CtxRow on={false} title="Other chats and images" detail="Not sent. Stay in your history." />
        </ul>
        <p className="mt-6 rounded-lg bg-canvas p-3 text-xs text-muted">
          Context size: small. Older messages are kept in your history but sent only as a summary.
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          {c.design_id && (
            <Link href={`/workspace/${c.design_id}?chat=${c.id}`} className={buttonVariants({ variant: "primary", size: "sm" })}>
              Continue
            </Link>
          )}
          {c.party_id && (
            <Link href={`/parties/${c.party_id}`} className={buttonVariants({ variant: "ghost", size: "sm" })}>
              Edit party summary →
            </Link>
          )}
        </div>
      </aside>
    </>
  );
}

function CtxRow({ on, title, detail }: { on: boolean; title: string; detail?: string | null }) {
  return (
    <li className="flex gap-3">
      <span className={cn("mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full", on ? "bg-green-50 text-ok" : "bg-canvas text-muted")}>
        {on ? <Check className="h-3.5 w-3.5" /> : <Minus className="h-3.5 w-3.5" />}
      </span>
      <div>
        <p className="text-sm font-medium">{title}</p>
        {detail && <p className="text-xs text-muted">{detail}</p>}
      </div>
    </li>
  );
}

